#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "click>=8.1.0",
#   "pyperclip>=1.8.2",
#   "anthropic>=0.5.0",
#   "prompt_toolkit>=3.0.0",
# ]
# ///

import sys
import os
import subprocess
import anthropic
import click
import pyperclip
import logging
import tempfile
from typing import Optional, List, Tuple, Any
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("ai-shell")

# Path to store commands for shell buffer injection
BUFFER_FILE = os.path.expanduser("~/.ai_shell_buffer")

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
        # Instantiate the Anthropic client (make sure ANTHROPIC_API_KEY is set)
        client = anthropic.Anthropic()
        
        # Create a message request with the prompt, specifically asking for a bash command
        response = client.messages.create(
            max_tokens=150,
            messages=[
                {"role": "user", "content": f"Provide a precise bash command to: {prompt_text}. Only return the exact command, no explanation."}
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
    
    # Use prompt_toolkit for better line editing
    command_history = InMemoryHistory()
    command_history.append_string(command)
    
    try:
        # This provides a full-featured line editor with history, cursor movement, etc.
        edited = prompt('> ', default=command, history=command_history)
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
        if result.stdout:
            click.echo(click.style("\nCommand Output:", fg="green"))
            click.echo(result.stdout)
        if result.stderr:
            click.echo(click.style("\nCommand Error Output:", fg="yellow"))
            click.echo(result.stderr)
        log.info("Command executed successfully")
        return True
    except subprocess.CalledProcessError as e:
        click.echo(click.style(f"Command failed with error: {e}", fg="red"))
        if e.stderr:
            click.echo(click.style(f"Error output: {e.stderr}", fg="red"))
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
        click.echo(click.style("\nCommand ready for buffer insertion!", fg="bright_green"))
        
        has_zsh_integration = detect_zsh_config()
        if has_zsh_integration:
            click.echo("Press Alt+i in your shell to insert it into your command line")
        else:
            click.echo("Paste the command in your terminal (it's also been copied to your clipboard)")
            click.echo("To enable keyboard shortcut (Alt+i), run: ai --setup-zsh")
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
        click.echo("ZSH integration is already set up.")
        return True
    
    try:
        # Add the integration code to .zshrc
        with open(zshrc_path, 'a') as f:
            f.write("\n" + setup_zsh_integration() + "\n")
        
        click.echo(click.style("ZSH integration installed successfully!", fg="green"))
        click.echo("To activate it, restart your terminal or run: source ~/.zshrc")
        click.echo("Then you can use Alt+i to insert AI-generated commands")
        return True
    except Exception as e:
        click.echo(click.style(f"Failed to install ZSH integration: {e}", fg="red"))
        return False

@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('prompt', nargs=-1, required=False)
@click.option('--execute/--no-execute', '-x/-n', default=None, 
              help="Automatically execute the command without prompting")
@click.option('--debug', is_flag=True, help="Enable debug logging")
@click.option('--setup-zsh', is_flag=True, help="Set up ZSH integration (adds code to ~/.zshrc)")
@click.option('--show-zsh-code', is_flag=True, help="Show ZSH integration code without installing")
def main(prompt: Tuple[str], execute: Optional[bool], debug: bool, 
         setup_zsh: bool, show_zsh_code: bool) -> bool:
    """
    AI-powered command line assistant.
    
    Generates a bash command based on your prompt and
    optionally executes it for you.
    
    Examples:
        ai list all files by size
        ai find all python files changed in the last week
        ai --setup-zsh
    """
    # Handle ZSH setup if requested
    if setup_zsh:
        return install_zsh_integration()
    
    if show_zsh_code:
        zsh_code = setup_zsh_integration()
        click.echo(zsh_code)
        click.echo("\n# Add the above code to your ~/.zshrc file")
        click.echo("# Then restart your shell or run 'source ~/.zshrc'")
        return True
    
    # Set debug logging if requested
    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")
    
    # Check if prompt is empty
    if not prompt:
        click.echo("Usage: ai <your prompt>")
        click.echo("Example: ai list all files in current directory by size")
        click.echo("\nOptions:")
        click.echo("  --setup-zsh       Set up ZSH integration")
        click.echo("  --show-zsh-code   Show ZSH integration code")
        click.echo("  --execute, -x     Automatically execute the command")
        click.echo("  --no-execute, -n  Don't execute, just show the command")
        click.echo("  --debug           Enable debug logging")
        return True
    
    # Combine all arguments to form the prompt
    prompt_text = " ".join(prompt)
    log.info(f"Processing prompt: {prompt_text}")
    
    try:
        with click.progressbar(
            length=100,
            label="Generating command",
            fill_char=click.style("=", fg="cyan"),
            empty_char=" "
        ) as bar:
            # Update progress
            bar.update(30)
            
            # Get the bash command
            bash_command = get_bash_command(prompt_text)
            
            # Complete progress
            bar.update(70)
        
        # Print the generated command
        click.echo(click.style("\nSuggested command:", fg="bright_blue"))
        click.echo(click.style(f"  {bash_command}", fg="bright_white", bold=True))
        click.echo()
        
        # Auto-execute if specified
        if execute is True:
            log.debug("Auto-executing command (--execute flag)")
            return execute_command(bash_command)
        elif execute is False:
            log.debug("Skipping execution (--no-execute flag)")
            inject_to_zsh_buffer(bash_command)
            click.echo(click.style("Command ready (--no-execute flag was used).", fg="blue"))
            return True
        
        # Ask for user approval
        while True:
            options = click.style("[y]", fg="green") + "/" + \
                     click.style("[n]", fg="red") + "/" + \
                     click.style("[e]", fg="yellow") + "/" + \
                     click.style("[c]", fg="blue") + "/" + \
                     click.style("[b]", fg="magenta")
            click.echo(f"Run this command? {options}: ", nl=False)
            approval = click.getchar().lower()
            click.echo()  # Add a newline after input
            log.debug(f"User selected option: {approval}")
            
            if approval == 'y':
                return execute_command(bash_command)
            elif approval == 'n':
                log.info("User cancelled command execution")
                click.echo("Command execution cancelled.")
                return True
            elif approval == 'e':
                log.debug("User chose to edit the command")
                # Show the current command and allow inline editing with proper line editing support
                click.echo("Edit command (use arrow keys, history, etc.):")
                edited_command = edit_command(bash_command)
                
                click.echo(click.style("\nEdited command:", fg="bright_blue"))
                click.echo(click.style(f"  {edited_command}", fg="bright_white", bold=True))
                click.echo()
                
                # Ask to run the edited command
                sub_options = click.style("[y]", fg="green") + "/" + \
                              click.style("[n]", fg="red") + "/" + \
                              click.style("[c]", fg="blue") + "/" + \
                              click.style("[b]", fg="magenta")
                click.echo(f"Run the edited command? {sub_options}: ", nl=False)
                sub_approval = click.getchar().lower()
                click.echo()  # Add a newline after input
                log.debug(f"User selected sub-option: {sub_approval}")
                
                if sub_approval == 'y':
                    return execute_command(edited_command)
                elif sub_approval == 'c':
                    pyperclip.copy(edited_command)
                    log.info("Command copied to clipboard")
                    click.echo(click.style("Command copied to clipboard!", fg="blue"))
                    return True
                elif sub_approval == 'b':
                    inject_to_zsh_buffer(edited_command)
                    return True
                else:
                    log.info("User cancelled edited command execution")
                    click.echo("Command execution cancelled.")
                    return True
            elif approval == 'c':
                pyperclip.copy(bash_command)
                log.info("Command copied to clipboard")
                click.echo(click.style("Command copied to clipboard!", fg="blue"))
                # After copying, ask if they want to run it
                sub_options = click.style("[y]", fg="green") + "/" + \
                              click.style("[n]", fg="red")
                click.echo(f"Also run the command? {sub_options}: ", nl=False)
                sub_approval = click.getchar().lower()
                click.echo()  # Add a newline after input
                log.debug(f"User selected sub-option: {sub_approval}")
                
                if sub_approval == 'y':
                    return execute_command(bash_command)
                else:
                    return True
            elif approval == 'b':
                log.debug("User chose to inject command to buffer")
                inject_to_zsh_buffer(bash_command)
                return True
            else:
                log.warning(f"Invalid input: {approval}")
                click.echo(f"Invalid input. Please enter 'y', 'n', 'e', 'c', or 'b'.")
    
    except Exception as e:
        log.exception(f"An error occurred: {e}")
        click.echo(click.style(f"An error occurred: {e}", fg="red"))
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
