"""Docker utilities for container management."""

import docker
import tarfile
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from utils.logger import get_logger
from config import config
from datetime import datetime, timedelta, timezone

# Label attached to every container started by this tool, so cleanup never
# touches unrelated containers on the host
CONTAINER_LABEL_KEY = "app"
CONTAINER_LABEL_VALUE = "omicairn-agent-local"

logger = get_logger(__name__)


class DockerManager:
    """Manages Docker containers for function block execution."""
    
    def __init__(self):
        try:
            # Initialize Docker client with longer timeout for API calls
            self.client = docker.from_env(timeout=3600)  # 1 hour timeout for API calls
            self.client.ping()
            logger.info("Docker client initialized successfully")
        except docker.errors.DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise RuntimeError("Docker is not available. Please ensure Docker is installed and running.")
    
    def pull_or_build_image(self, image_name: str, dockerfile_path: Optional[Path] = None) -> bool:
        """Pull image from registry or build from Dockerfile."""
        try:
            # First try to find the image locally
            try:
                self.client.images.get(image_name)
                logger.info(f"Image {image_name} found locally")
                return True
            except docker.errors.ImageNotFound:
                pass
            
            # Try to pull from registry
            logger.info(f"Pulling image {image_name}...")
            try:
                self.client.images.pull(image_name)
                logger.info(f"Successfully pulled {image_name}")
                return True
            except docker.errors.APIError:
                logger.warning(f"Failed to pull {image_name}")
            
            # Build from Dockerfile if provided
            if dockerfile_path and dockerfile_path.exists():
                logger.info(f"Building image {image_name} from {dockerfile_path}")
                self.client.images.build(
                    path=str(dockerfile_path.parent),
                    dockerfile=dockerfile_path.name,
                    tag=image_name,
                    rm=True
                )
                logger.info(f"Successfully built {image_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error managing image {image_name}: {e}")
            return False
    
    def run_container(
        self,
        image: str,
        command: Optional[List[str]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        environment: Optional[Dict[str, str]] = None,
        working_dir: str = "/workspace",
        timeout: int = 300,
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[float] = None,
        auto_remove: bool = True  # Changed default to True for automatic cleanup
    ) -> Tuple[int, str, str]:
        """Run a Docker container and return exit code, stdout, and stderr.
        
        Args:
            auto_remove: If True, container will be removed after execution (default: True)
        """
        
        container = None
        try:
            # Prepare container configuration
            container_config = {
                "image": image,
                "command": command,
                "volumes": volumes or {},
                "environment": environment or {},
                "working_dir": working_dir,
                "detach": True,
                "remove": False,  # We handle removal manually in finally block for better control
                "mem_limit": memory_limit or config.container_memory_limit,
                "nano_cpus": int((cpu_limit or config.container_cpu_limit) * 1e9),
                "network_mode": "bridge",
                "labels": {CONTAINER_LABEL_KEY: CONTAINER_LABEL_VALUE}
            }
            
            # Create and start container
            logger.info(f"Starting container with image {image}")
            container = self.client.containers.run(**container_config)
            
            # Wait for container to complete
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", -1)
            
            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode("utf-8")
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8") 
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8")
            
            logger.info(f"Container exited with code {exit_code}")
            
            return exit_code, stdout, stderr
            
        except docker.errors.ContainerError as e:
            logger.error(f"Container error: {e}")
            return e.exit_status, "", str(e)
        except docker.errors.ImageNotFound as e:
            logger.error(f"Image not found: {e}")
            return -1, "", f"Image not found: {image}"
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
            if "Read timed out" in str(e):
                logger.error(f"Docker API timeout - container may still be running. Consider increasing timeout (current: {timeout}s)")
            return -1, "", str(e)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            if "Read timed out" in str(e):
                logger.error(f"Docker communication timeout - container may still be running")
            return -1, "", str(e)
        finally:
            # Clean up container if auto_remove is enabled (default: True)
            if container and auto_remove:
                try:
                    # First try to stop the container gracefully if it's still running
                    try:
                        container.reload()  # Refresh container state
                        if container.status == 'running':
                            logger.debug(f"Stopping container {container.id[:12]}")
                            container.stop(timeout=10)
                    except docker.errors.NotFound:
                        pass  # Container already stopped/removed
                    except Exception as e:
                        logger.debug(f"Could not stop container: {e}")
                    
                    # Now remove the container
                    container.remove(force=True)
                    logger.debug(f"Successfully removed container {container.id[:12]}")
                except docker.errors.NotFound:
                    # Container already removed - this is fine
                    logger.debug(f"Container {container.id[:12]} already removed")
                except docker.errors.APIError as e:
                    # Log but don't raise - we're in finally block
                    logger.warning(f"Could not remove container {container.id[:12]}: {e}")
            elif container and not auto_remove:
                logger.debug(f"Container {container.id[:12]} preserved (auto_remove=False)")
    
    def copy_to_container(self, container, src_path: Path, dst_path: str) -> bool:
        """Copy files to a running container."""
        try:
            # Create tar archive in memory
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tar.add(src_path, arcname=Path(dst_path).name)
            tar_stream.seek(0)
            
            # Copy to container
            container.put_archive(Path(dst_path).parent, tar_stream)
            return True
        except Exception as e:
            logger.error(f"Failed to copy to container: {e}")
            return False
    
    def copy_from_container(self, container, src_path: str, dst_path: Path) -> bool:
        """Copy files from a running container."""
        try:
            # Get archive from container
            bits, stat = container.get_archive(src_path)
            
            # Extract to destination
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                try:
                    # Python >= 3.12 (and patched 3.8+): reject unsafe members
                    tar.extractall(dst_path.parent, filter="data")
                except TypeError:
                    # Older Python without extraction filters: validate member paths manually
                    base = dst_path.parent.resolve()
                    for member in tar.getmembers():
                        target = (base / member.name).resolve()
                        if not str(target).startswith(str(base)) or member.issym() or member.islnk():
                            raise ValueError(f"Unsafe path in container archive: {member.name}")
                    tar.extractall(dst_path.parent)
            
            return True
        except Exception as e:
            logger.error(f"Failed to copy from container: {e}")
            return False
    
    def list_containers(self, all: bool = False) -> List[Dict]:
        """List containers."""
        containers = self.client.containers.list(all=all)
        return [
            {
                "id": c.short_id,
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id
            }
            for c in containers
        ]
    
    def cleanup_old_containers(self, hours: int = 24) -> int:
        """Remove stopped containers created by this tool that finished more than `hours` ago."""
        count = 0
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            containers = self.client.containers.list(
                all=True,
                filters={"status": "exited", "label": f"{CONTAINER_LABEL_KEY}={CONTAINER_LABEL_VALUE}"},
            )
            for container in containers:
                finished_at = container.attrs.get("State", {}).get("FinishedAt", "")
                try:
                    # Docker timestamps look like 2024-01-01T12:00:00.123456789Z
                    finished = datetime.fromisoformat(finished_at[:19]).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if finished < cutoff:
                    container.remove()
                    count += 1
            logger.info(f"Cleaned up {count} old containers")
        except Exception as e:
            logger.error(f"Error cleaning up containers: {e}")
        return count
    
