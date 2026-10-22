"""Command-line interface for OmiCairn Agent Local."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
import sys

from .agents import MainAgent
from .utils.logger import setup_logger
from .config import config
from .constants import DEFAULT_OPENAI_MODEL, ENV_OPENAI_API_KEY

console = Console()
logger = setup_logger()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """OmiCairn Agent Local - LLM-guided single-cell analysis tool."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.argument("request", type=str)
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--max-nodes", type=int, default=20, help="Maximum number of analysis nodes")
@click.option("--max-children", type=int, default=3, help="Maximum children per node")
@click.option("--max-debug-trials", type=int, default=3, help="Maximum debug attempts per node")
@click.option("--mode", type=click.Choice(["mixed", "only_new", "only_existing"]), default="mixed", help="Generation mode")
@click.option("--model", type=str, default=DEFAULT_OPENAI_MODEL, help="OpenAI model to use")
@click.option("--api-key", type=str, envvar=ENV_OPENAI_API_KEY, help="OpenAI API key")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def analyze(input_file, request, output, max_nodes, max_children, max_debug_trials, mode, model, api_key, verbose):
    """Run hierarchical analysis on single-cell data."""
    
    try:
        # Validate API key
        if not api_key:
            console.print(f"[red]Error:[/red] OpenAI API key not provided. Set {ENV_OPENAI_API_KEY} environment variable or use --api-key option.")
            sys.exit(1)
        
        # Create agent
        console.print("[bold blue]Initializing OmiCairn Agent...[/bold blue]")
        agent = MainAgent(openai_api_key=api_key)
        
        # Run analysis
        result = agent.run_analysis(
            input_data_path=input_file,
            user_request=request,
            output_dir=output,
            max_nodes=max_nodes,
            max_children=max_children,
            max_debug_trials=max_debug_trials,
            generation_mode=mode,
            llm_model=model,
            verbose=verbose
        )
        
        # Success message
        console.print(f"\n[green]Analysis completed successfully![/green]")
        console.print(f"Results saved to: {result['output_dir']}")
        
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        if verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
def validate():
    """Validate the execution environment."""
    
    console.print("[bold]Validating environment...[/bold]\n")
    
    try:
        agent = MainAgent()
        validation = agent.validate_environment()
        
        # Display results
        table = Table(title="Environment Validation")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        
        for component, status in validation.items():
            status_text = "[green]✓ Available[/green]" if status else "[red]✗ Not Available[/red]"
            table.add_row(component.replace("_", " ").title(), status_text)
        
        console.print(table)
        
        # Check if all components are available
        if all(validation.values()):
            console.print("\n[green]All components are properly configured![/green]")
        else:
            console.print("\n[yellow]Some components are missing. Please check the setup instructions.[/yellow]")
            
            if not validation.get("docker_available"):
                console.print("\n[red]Docker is not available.[/red] Please ensure Docker is installed and running.")
            
            if not validation.get("python_image"):
                console.print("\n[yellow]Python Docker image not found.[/yellow]")
                console.print(f"Build it with: docker build -t {config.python_image} -f docker/Dockerfile.python docker/  (or run docker/build.sh)")
            
            if not validation.get("r_image"):
                console.print("\n[yellow]R Docker image not found.[/yellow]")
                console.print(f"Build it with: docker build -t {config.r_image} -f docker/Dockerfile.r.minimal docker/  (or run docker/build.sh)")
        
    except Exception as e:
        console.print(f"[red]Error during validation:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument("tree_file", type=click.Path(exists=True))
def inspect(tree_file):
    """Inspect a saved analysis tree."""
    
    try:
        from .analysis_tree_management import AnalysisTreeManager
        
        manager = AnalysisTreeManager()
        tree = manager.load_tree(Path(tree_file))
        
        # Display tree info
        console.print(f"[bold]Analysis Tree[/bold]: {tree.id}")
        console.print(f"[bold]User Request[/bold]: {tree.user_request}")
        console.print(f"[bold]Created[/bold]: {tree.created_at}")
        console.print()
        
        # Display nodes
        table = Table(title="Analysis Nodes")
        table.add_column("Level", style="cyan")
        table.add_column("Name", style="yellow")
        table.add_column("Status", style="green")
        table.add_column("Duration", style="magenta")
        
        # Sort nodes by level and add to table
        sorted_nodes = sorted(tree.nodes.values(), key=lambda n: (n.level, n.created_at))
        
        for node in sorted_nodes:
            status_icon = {
                "completed": "[green]✓[/green]",
                "failed": "[red]✗[/red]",
                "pending": "[yellow]○[/yellow]",
                "running": "[blue]●[/blue]"
            }.get(node.state, "?")
            
            duration = f"{node.duration:.1f}s" if node.duration else "-"
            indent = "  " * node.level
            
            table.add_row(
                str(node.level),
                f"{indent}{node.function_block.name}",
                f"{status_icon} {node.state}",
                duration
            )
        
        console.print(table)
        
        # Display summary
        summary = manager.get_summary()
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"Total Nodes: {summary['total_nodes']}")
        console.print(f"Completed: [green]{summary['completed_nodes']}[/green]")
        console.print(f"Failed: [red]{summary['failed_nodes']}[/red]")
        console.print(f"Total Duration: {summary['total_duration_seconds']:.1f}s")
        
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()