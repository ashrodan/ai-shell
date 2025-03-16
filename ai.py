#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "click>=8.1.0",
#   "pyperclip>=1.8.2",
#   "anthropic>=0.5.0",
#   "prompt_toolkit>=3.0.0",
#   "pyyaml>=6.0",
#   "rich>=12.0.0",
# ]
# ///

import sys
import os
import subprocess
import anthropic
import click
import pyperclip
import logging
import yaml
import json
import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("ai-shell")

# Path to store commands for shell buffer injection
BUFFER_FILE = os.path.expanduser("~/.ai_shell_buffer")
# Directory for session history
HISTORY_DIR = os.path.expanduser("~/.ai_shell_history")
# File for command history in interactive mode
COMMAND_HISTORY_FILE = os.path.expanduser("~/.ai_shell_command_history")

# Create history directory if it doesn't exist
os.makedirs(HISTORY_DIR, exist_ok=True)

# Rich console for pretty output
console = Console()

def get_bash_command(prompt_text: str) -> str:
    """
    Get a bash command from Anthropic's Claude that fulfills the given prompt.
    
    Args:
        prompt_text: The user's request in natural language
        
    Returns:
        str: The generated bash command
    """
    log.info(f"Generating command for prompt: {prompt_text}")
    
    try:
        # Explicitly get API key from environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            log.error("ANTHROPIC_API_KEY environment variable is not set")
            raise ValueError("ANTHROPIC_API_KEY not found. Please set it with: export ANTHROPIC_API_KEY='your_api_key'")
            
        # Instantiate the Anthropic client with explicit API key
        client = anthropic.Anthropic(api_key=api_key)
        
        # Create a message request with the prompt, specifically asking for a bash command
        response = client.messages.create(
            max_tokens=150,
            messages=[
                {"role": "user", "content": f"Provide a precise bash command to: {prompt_text}. Only return the exact command, no explanation. Ensure it works for Mac/Linux, keep it simple."}
            ],
            model="claude-3-5-sonnet-latest"
        )
        
        # Extract the first line of the response (the command)
        command = response.content[0].text.strip()
        log.info(f"Generated command: {command}")
        return command
    except Exception as e:
        log.error(f"Error generating command: {e}")
        raise

def edit_command(command: str) -> str:
    """
    Allow the user to edit the command with full-featured line editing.
    
    Args:
        command: The initial command to edit
        
    Returns:
        str: The edited command
    """
    log.debug(f"Editing command: {command}")
    
    session = PromptSession()
    
    try:
        # This provides a full-featured line editor with history, cursor movement, etc.
        edited = session.prompt('> ', default=command, auto_suggest=AutoSuggestFromHistory())
        log.debug(f"Command after editing: {edited}")
        return edited
    except Exception as e:
        log.error(f"Error during command editing: {e}")
        # Fall back to the original command if editing fails
        return command

def execute_command(command: str) -> bool:
    """
    Execute the bash command and display the output
    
    Args:
        command: The bash command to execute
        
    Returns:
        bool: True if command executed successfully, False otherwise
    """
    log.info(f"Executing command: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, 
                               text=True, capture_output=True)
        
        # Use rich for prettier output
        if result.stdout:
            console.print("\n[bold green]Command Output:[/bold green]")
            console.print(result.stdout)
        if result.stderr:
            console.print("\n[bold yellow]Command Error Output:[/bold yellow]")
            console.print(result.stderr)
            
        log.info("Command executed successfully")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"\n[bold red]Command failed with error: {e}[/bold red]")
        if e.stderr:
            console.print(f"[red]Error output: {e.stderr}[/red]")
        log.error(f"Command execution failed: {e}")
        return False

def inject_to_zsh_buffer(command: str) -> bool:
    """
    Inject the command into the Zsh buffer for the user to edit/execute
    
    Args:
        command: The command to inject into the buffer
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create .ai_shell_buffer file with the command
        with open(BUFFER_FILE, 'w') as f:
            f.write(command)
        log.info(f"Command saved to buffer file: {BUFFER_FILE}")
        
        # Also copy to clipboard as fallback
        pyperclip.copy(command)
        
        # Display instructions for first-time users
        console.print("\n[bold green]Command ready for buffer insertion![/bold green]")
        
        has_zsh_integration = detect_zsh_config()
        if has_zsh_integration:
            console.print("Press [bold]Alt+i[/bold] in your shell to insert it into your command line")
        else:
            console.print("Paste the command in your terminal (it's also been copied to your clipboard)")
            console.print("To enable keyboard shortcut (Alt+i), run: [bold]ai --setup-zsh[/bold]")
        return True
        
    except Exception as e:
        log.error(f"Failed to prepare buffer injection: {e}")
        return False

def detect_zsh_config() -> bool:
    """Check if the Zsh configuration has been set up for AI Shell buffer injection"""
    zshrc_path = os.path.expanduser("~/.zshrc")
    
    try:
        if os.path.exists(zshrc_path):
            with open(zshrc_path, 'r') as f:
                content = f.read()
                return "ai-shell-inject-buffer" in content
        return False
    except:
        return False

def setup_zsh_integration() -> str:
    """
    Generate Zsh configuration code for command line buffer injection
    
    Returns:
        str: Zsh configuration code to add to .zshrc
    """
    return """
# AI Shell ZSH integration
function ai-shell-inject-buffer() {
    local cmd
    if [[ -f "${HOME}/.ai_shell_buffer" ]]; then
        cmd=$(cat "${HOME}/.ai_shell_buffer")
        BUFFER="${cmd}"
        zle redisplay
    fi
}

zle -N ai-shell-inject-buffer
bindkey '^[i' ai-shell-inject-buffer  # Alt+i
"""

def install_zsh_integration() -> bool:
    """
    Automatically install the ZSH integration to the user's .zshrc file
    
    Returns:
        bool: True if successful, False otherwise
    """
    zshrc_path = os.path.expanduser("~/.zshrc")
    
    if detect_zsh_config():
        console.print("ZSH integration is already set up.")
        return True
    
    try:
        # Add the integration code to .zshrc
        with open(zshrc_path, 'a') as f:
            f.write("\n" + setup_zsh_integration() + "\n")
        
        console.print("[bold green]ZSH integration installed successfully![/bold green]")
        console.print("To activate it, restart your terminal or run: [bold]source ~/.zshrc[/bold]")
        console.print("Then you can use [bold]Alt+i[/bold] to insert AI-generated commands")
        return True
    except Exception as e:
        console.print(f"[bold red]Failed to install ZSH integration: {e}[/bold red]")
        return False

def save_session(session_data: Dict[str, Any], session_name: Optional[str] = None) -> str:
    """
    Save the current interactive session to a file
    
    Args:
        session_data: Dictionary containing session data
        session_name: Optional name for the session file
        
    Returns:
        str: Path to the saved session file
    """
    if not session_name:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{timestamp}"
    
    if not session_name.endswith('.yaml'):
        session_name += '.yaml'
    
    session_path = os.path.join(HISTORY_DIR, session_name)
    
    try:
        with open(session_path, 'w') as f:
            yaml.dump(session_data, f, default_flow_style=False)
        log.info(f"Session saved to: {session_path}")
        return session_path
    except Exception as e:
        log.error(f"Failed to save session: {e}")
        raise

def load_session(session_path: str) -> Dict[str, Any]:
    """
    Load a saved session from a file
    
    Args:
        session_path: Path to the session file
        
    Returns:
        dict: Loaded session data
    """
    try:
        with open(session_path, 'r') as f:
            session_data = yaml.safe_load(f)
        log.info(f"Session loaded from: {session_path}")
        return session_data
    except Exception as e:
        log.error(f"Failed to load session: {e}")
        raise

def list_sessions() -> List[str]:
    """
    List all saved sessions
    
    Returns:
        list: List of session file paths
    """
    try:
        sessions = [f for f in os.listdir(HISTORY_DIR) if f.endswith('.yaml')]
        return sorted(sessions)
    except Exception as e:
        log.error(f"Failed to list sessions: {e}")
        return []

def interactive_mode():
    """
    Run the AI Shell in interactive mode with session management
    """
    console.print("\n[bold blue]AI Shell - Interactive Mode[/bold blue]")
    console.print("Type [bold green]help[/bold green] for available commands or [bold red]exit[/bold red] to quit.")
    
    # Set up command history
    history_file = FileHistory(COMMAND_HISTORY_FILE)
    session = PromptSession(history=history_file)
    
    # Available commands for auto-completion
    command_completer = WordCompleter([
        'help', 'exit', 'save', 'load', 'list', 'history', 'clear',
    ])
    
    # Current session data
    current_session = {
        'commands': [],
        'metadata': {
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat(),
        }
    }
    
    while True:
        try:
            # Get user input with pretty prompt and auto-completion
            user_input = session.prompt(
                HTML('<ansiblue>ai></ansiblue> '), 
                completer=command_completer,
                auto_suggest=AutoSuggestFromHistory()
            )
            
            # Handle special commands
            if user_input.lower() in ('exit', 'quit'):
                # Ask to save session before exiting
                if current_session['commands'] and console.input("[yellow]Save session before exiting? (y/n): [/yellow]").lower() == 'y':
                    session_name = console.input("[green]Enter session name (or press Enter for auto-name): [/green]")
                    save_path = save_session(current_session, session_name or None)
                    console.print(f"[green]Session saved to: {save_path}[/green]")
                console.print("[blue]Goodbye![/blue]")
                break
                
            elif user_input.lower() == 'help':
                help_table = Table(title="AI Shell Commands")
                help_table.add_column("Command", style="cyan")
                help_table.add_column("Description", style="green")
                
                help_table.add_row("help", "Show this help message")
                help_table.add_row("exit, quit", "Exit the interactive mode")
                help_table.add_row("save [name]", "Save the current session")
                help_table.add_row("load <name>", "Load a saved session")
                help_table.add_row("list", "List all saved sessions")
                help_table.add_row("history", "Show command history in current session")
                help_table.add_row("clear", "Clear the screen")
                help_table.add_row("<any other text>", "Generate and manage a bash command")
                
                console.print(help_table)
                continue
                
            elif user_input.lower().startswith('save'):
                parts = user_input.split(maxsplit=1)
                session_name = parts[1] if len(parts) > 1 else None
                
                current_session['metadata']['updated_at'] = datetime.datetime.now().isoformat()
                save_path = save_session(current_session, session_name)
                console.print(f"[green]Session saved to: {save_path}[/green]")
                continue
                
            elif user_input.lower().startswith('load'):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    console.print("[yellow]Please specify a session name to load[/yellow]")
                    continue
                    
                session_name = parts[1]
                if not session_name.endswith('.yaml'):
                    session_name += '.yaml'
                    
                session_path = os.path.join(HISTORY_DIR, session_name)
                
                try:
                    loaded_session = load_session(session_path)
                    current_session = loaded_session
                    console.print(f"[green]Loaded session: {session_name}[/green]")
                    
                    # Display the commands from the loaded session
                    console.print("\n[bold]Session commands:[/bold]")
                    for idx, cmd_data in enumerate(current_session['commands'], 1):
                        console.print(f"[blue]{idx}.[/blue] [yellow]Prompt:[/yellow] {cmd_data['prompt']}")
                        console.print(f"   [green]Command:[/green] {cmd_data['command']}")
                        console.print()
                except Exception as e:
                    console.print(f"[red]Failed to load session: {e}[/red]")
                continue
                
            elif user_input.lower() == 'list':
                sessions = list_sessions()
                if sessions:
                    console.print("\n[bold]Saved sessions:[/bold]")
                    for idx, session_name in enumerate(sessions, 1):
                        session_path = os.path.join(HISTORY_DIR, session_name)
                        try:
                            with open(session_path, 'r') as f:
                                session_data = yaml.safe_load(f)
                                cmd_count = len(session_data.get('commands', []))
                                created = session_data.get('metadata', {}).get('created_at', 'Unknown')
                                if isinstance(created, str):
                                    # Try to parse and format the date
                                    try:
                                        created_dt = datetime.datetime.fromisoformat(created)
                                        created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
                                    except:
                                        pass
                        except:
                            cmd_count = "?"
                            created = "Unknown"
                            
                        console.print(f"[blue]{idx}.[/blue] [green]{session_name}[/green] - {cmd_count} commands, created: {created}")
                else:
                    console.print("[yellow]No saved sessions found[/yellow]")
                continue
                
            elif user_input.lower() == 'history':
                if current_session['commands']:
                    console.print("\n[bold]Command history:[/bold]")
                    for idx, cmd_data in enumerate(current_session['commands'], 1):
                        console.print(f"[blue]{idx}.[/blue] [yellow]Prompt:[/yellow] {cmd_data['prompt']}")
                        console.print(f"   [green]Command:[/green] {cmd_data['command']}")
                        console.print()
                else:
                    console.print("[yellow]No commands in current session[/yellow]")
                continue
                
            elif user_input.lower() == 'clear':
                console.clear()
                continue
                
            # Process normal input as a command generation request
            if not user_input.strip():
                continue
                
            # Generate bash command
            with console.status("[bold green]Generating command...[/bold green]"):
                bash_command = get_bash_command(user_input)
            
            # Display the generated command
            console.print("\n[bold blue]Suggested command:[/bold blue]")
            console.print(Syntax(bash_command, "bash", theme="monokai", line_numbers=False))
            
            # Add to session history
            command_entry = {
                'prompt': user_input,
                'command': bash_command,
                'timestamp': datetime.datetime.now().isoformat(),
                'executed': False,
                'output': None,
            }
            current_session['commands'].append(command_entry)
            current_session['metadata']['updated_at'] = datetime.datetime.now().isoformat()
            
            # Ask for user action
            console.print("\nOptions:")
            console.print("[bold green]e[/bold green]: Edit command")
            console.print("[bold blue]c[/bold blue]: Copy to clipboard")
            console.print("[bold magenta]b[/bold magenta]: Insert to shell buffer (for Alt+i)")
            console.print("[bold yellow]r[/bold yellow]: Run command")
            console.print("[bold red]s[/bold red]: Skip")
            
            choice = console.input("Choose an option: ").lower()
            
            if choice == 'e':
                # Edit the command
                console.print("\n[bold]Edit command (use arrow keys, history, etc.):[/bold]")
                edited_command = edit_command(bash_command)
                
                console.print("\n[bold blue]Edited command:[/bold blue]")
                console.print(Syntax(edited_command, "bash", theme="monokai", line_numbers=False))
                
                # Update the command in history
                current_session['commands'][-1]['command'] = edited_command
                
                # Ask for action on edited command
                console.print("\nOptions:")
                console.print("[bold blue]c[/bold blue]: Copy to clipboard")
                console.print("[bold magenta]b[/bold magenta]: Insert to shell buffer (for Alt+i)")
                console.print("[bold yellow]r[/bold yellow]: Run command")
                console.print("[bold red]s[/bold red]: Skip")
                
                sub_choice = console.input("Choose an option: ").lower()
                
                if sub_choice == 'c':
                    pyperclip.copy(edited_command)
                    console.print("[blue]Command copied to clipboard![/blue]")
                elif sub_choice == 'b':
                    inject_to_zsh_buffer(edited_command)
                elif sub_choice == 'r':
                    result = execute_command(edited_command)
                    current_session['commands'][-1]['executed'] = True
                    # We don't capture the output here, but we could
            
            elif choice == 'c':
                pyperclip.copy(bash_command)
                console.print("[blue]Command copied to clipboard![/blue]")
            
            elif choice == 'b':
                inject_to_zsh_buffer(bash_command)
            
            elif choice == 'r':
                result = execute_command(bash_command)
                current_session['commands'][-1]['executed'] = True
            
            # Add a blank line for readability
            console.print()
            
        except KeyboardInterrupt:
            # Handle Ctrl+C by asking if user wants to exit
            console.print("\n[yellow]Ctrl+C pressed. Exit? (y/n): [/yellow]", end="")
            try:
                if console.input().lower() == 'y':
                    console.print("[blue]Goodbye![/blue]")
                    break
            except:
                pass
        
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")
            log.exception("Error in interactive mode")

@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('prompt', nargs=-1, required=False)
@click.option('--execute/--no-execute', '-x/-n', default=None, 
              help="Automatically execute the command without prompting")
@click.option('--debug', is_flag=True, help="Enable debug logging")
@click.option('--setup-zsh', is_flag=True, help="Set up ZSH integration (adds code to ~/.zshrc)")
@click.option('--show-zsh-code', is_flag=True, help="Show ZSH integration code without installing")
@click.option('--interactive', '-i', is_flag=True, help="Run in interactive mode with session management")
def main(prompt: Tuple[str], execute: Optional[bool], debug: bool, 
         setup_zsh: bool, show_zsh_code: bool, interactive: bool) -> bool:
    """
    AI-powered command line assistant.
    
    Generates a bash command based on your prompt and
    optionally executes it for you.
    
    Examples:
        ai list all files by size
        ai find all python files changed in the last week
        ai --interactive
        ai --setup-zsh
    """
    # Set debug logging if requested
    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")
    
    # Handle ZSH setup if requested
    if setup_zsh:
        return install_zsh_integration()
    
    if show_zsh_code:
        zsh_code = setup_zsh_integration()
        console.print(zsh_code)
        console.print("\n# Add the above code to your ~/.zshrc file")
        console.print("# Then restart your shell or run 'source ~/.zshrc'")
        return True
    
    # Run in interactive mode if requested
    if interactive:
        interactive_mode()
        return True
    
    # Check if prompt is empty
    if not prompt:
        console.print("Usage: ai <your prompt>")
        console.print("Example: ai list all files in current directory by size")
        console.print("\nOptions:")
        console.print("  --interactive, -i   Run in interactive mode with session management")
        console.print("  --setup-zsh         Set up ZSH integration")
        console.print("  --show-zsh-code     Show ZSH integration code")
        console.print("  --execute, -x       Automatically execute the command")
        console.print("  --no-execute, -n    Don't execute, just show the command")
        console.print("  --debug             Enable debug logging")
        return True
    
    # Combine all arguments to form the prompt
    prompt_text = " ".join(prompt)
    log.info(f"Processing prompt: {prompt_text}")
    
    try:
        with console.status("[bold green]Generating command...[/bold green]"):
            # Get the bash command
            bash_command = get_bash_command(prompt_text)
        
        # Print the generated command
        console.print("\n[bold blue]Suggested command:[/bold blue]")
        console.print(Syntax(bash_command, "bash", theme="monokai", line_numbers=False))
        
        # Auto-execute if specified
        if execute is True:
            log.debug("Auto-executing command (--execute flag)")
            return execute_command(bash_command)
        elif execute is False:
            log.debug("Skipping execution (--no-execute flag)")
            inject_to_zsh_buffer(bash_command)
            console.print("[blue]Command ready (--no-execute flag was used).[/blue]")
            return True
        
        # Ask for user approval
        console.print("\nOptions:")
        console.print("[bold green]y[/bold green]: Run command")
        console.print("[bold red]n[/bold red]: Cancel")
        console.print("[bold yellow]e[/bold yellow]: Edit command")
        console.print("[bold blue]c[/bold blue]: Copy to clipboard")
        console.print("[bold magenta]b[/bold magenta]: Insert to shell buffer (for Alt+i)")
        
        while True:
            choice = console.input("Choose an option: ").lower()
            log.debug(f"User selected option: {choice}")
            
            if choice == 'y':
                return execute_command(bash_command)
            elif choice == 'n':
                log.info("User cancelled command execution")
                console.print("[yellow]Command execution cancelled.[/yellow]")
                return True
            elif choice == 'e':
                log.debug("User chose to edit the command")
                # Show the current command and allow inline editing with proper line editing support
                console.print("\n[bold]Edit command (use arrow keys, history, etc.):[/bold]")
                edited_command = edit_command(bash_command)
                
                console.print("\n[bold blue]Edited command:[/bold blue]")
                console.print(Syntax(edited_command, "bash", theme="monokai", line_numbers=False))
                
                # Ask to run the edited command
                console.print("\nOptions:")
                console.print("[bold green]y[/bold green]: Run command")
                console.print("[bold red]n[/bold red]: Cancel")
                console.print("[bold blue]c[/bold blue]: Copy to clipboard")
                console.print("[bold magenta]b[/bold magenta]: Insert to shell buffer (for Alt+i)")
                
                sub_choice = console.input("Choose an option: ").lower()
                log.debug(f"User selected sub-option: {sub_choice}")
                
                if sub_choice == 'y':
                    return execute_command(edited_command)
                elif sub_choice == 'c':
                    pyperclip.copy(edited_command)
                    log.info("Command copied to clipboard")
                    console.print("[blue]Command copied to clipboard![/blue]")
                    return True
                elif sub_choice == 'b':
                    inject_to_zsh_buffer(edited_command)
                    return True
                else:
                    log.info("User cancelled edited command execution")
                    console.print("[yellow]Command execution cancelled.[/yellow]")
                    return True
            elif choice == 'c':
                pyperclip.copy(bash_command)
                log.info("Command copied to clipboard")
                console.print("[blue]Command copied to clipboard![/blue]")
                # After copying, ask if they want to run it
                if console.input("Also run the command? (y/n): ").lower() == 'y':
                    return execute_command(bash_command)
                else:
                    return True
            elif choice == 'b':
                log.debug("User chose to inject command to buffer")
                inject_to_zsh_buffer(bash_command)
                return True
            else:
                log.warning(f"Invalid input: {choice}")
                console.print(f"[red]Invalid input. Please enter 'y', 'n', 'e', 'c', or 'b'.[/red]")
    
    except Exception as e:
        log.exception(f"An error occurred: {e}")
        console.print(f"[bold red]An error occurred: {e}[/bold red]")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
