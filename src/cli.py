import sys
import json
import logging
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Callable, Dict, List
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from src.agent import ZerePyAgent
from src.helpers import print_h_bar

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("cli")

@dataclass
class Command:
    """Dataclass to represent a CLI command"""
    name: str
    description: str
    tips: List[str]
    handler: Callable
    aliases: List[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

class ZerePyCLI:
    def __init__(self):
        self.agent = None
        
        # Create config directory if it doesn't exist
        self.config_dir = Path.home() / '.zerepy'
        self.config_dir.mkdir(exist_ok=True)
        
        # Initialize command registry
        self._initialize_commands()
        
        # Setup prompt toolkit components
        self._setup_prompt_toolkit()

    def _initialize_commands(self) -> None:
        """Initialize all CLI commands"""
        self.commands: Dict[str, Command] = {}
        
        # Help command
        self._register_command(
            Command(
                name="help",
                description="Displays a list of all available commands, or help for a specific command.",
                tips=["Try 'help' to see available commands.",
                      "Try 'help {command}' to get more information about a specific command."],
                handler=self.help,
                aliases=['h', '?']
            )
        )

        # Clear command
        self._register_command(
            Command(
                name="clear",
                description="Clears the terminal screen.",
                tips=["Use this command to clean up your terminal view"],
                handler=self.clear_screen,
                aliases=['cls']
            )
        )
        
        ################## AGENTS ################## 
        # Agent action command
        self._register_command(
            Command(
                name="agent-action",
                description="Runs a single agent action.",
                tips=["Format: agent-action {connection} {action}",
                      "Use 'list-connections' to see available connections.",
                      "Use 'list-actions' to see available actions."],
                handler=self.agent_action,
                aliases=['action', 'run']
            )
        )
        
        # Agent loop command
        self._register_command(
            Command(
                name="agent-loop",
                description="Starts the current agent's autonomous behavior loop.",
                tips=["Press Ctrl+C to stop the loop"],
                handler=self.agent_loop,
                aliases=['loop', 'start']
            )
        )
        
        # List agents command
        self._register_command(
            Command(
                name="list-agents",
                description="Lists all available agents you have on file.",
                tips=["Agents are stored in the 'agents' directory",
                      "Use 'load-agent' to load an available agent"],
                handler=self.list_agents,
                aliases=['agents', 'ls-agents']
            )
        )
        
        # Load agent command
        self._register_command(
            Command(
                name="load-agent",
                description="Loads an agent from a file.",
                tips=["Format: load-agent {agent_name}",
                      "Use 'list-agents' to see available agents"],
                handler=self.load_agent,
                aliases=['load']
            )
        )
        
        # Create agent command
        self._register_command(
            Command(
                name="create-agent",
                description="Creates a new agent.",
                tips=["Follow the interactive wizard to create a new agent"],
                handler=self.create_agent,
                aliases=['new-agent', 'create']
            )
        )
        
        # Define default agent
        self._register_command(
            Command(
                name="set-default-agent",
                description="Define which model is loaded when the CLI starts.",
                tips=["You can also just change the 'default_agent' field in agents/general.json"],
                handler=self.set_default_agent,
                aliases=['default']
            )
        )

        # Chat command
        self._register_command(
            Command(
                name="chat",
                description="Start a chat session with the current agent",
                tips=["Use 'exit' to end the chat session"],
                handler=self.chat_session,
                aliases=['talk']
            )
        )

        # Memory commands
        self._register_command(
            Command(
                name="upload-document",
                description="Upload a document to the agent's memory",
                tips=["Format: upload-document {filepath} {category}",
                    "Example: upload-document theory.pdf music_theory"],
                handler=self.upload_document,
                aliases=['upload', 'learn']
            )
        )
        
        self._register_command(
            Command(
                name="search-memory",
                description="Search the agent's memory",
                tips=["Format: search-memory {category} {query}",
                    "Example: search-memory music_theory 'chord progressions'"],
                handler=self.search_memory,
                aliases=['recall', 'remember']
            )
        )

        self._register_command(
            Command(
                name="list-memory-categories",
                description="List all memory categories and their sizes",
                tips=["Shows all categories and how many memories each contains"],
                handler=self.list_memory_categories,
                aliases=['categories', 'ls-mem']
            )
        )

        self._register_command(
            Command(
                name="delete-memory-category",
                description="Delete all memories in a category",
                tips=["Format: delete-memory-category {category}",
                    "WARNING: This will permanently delete all memories in the category"],
                handler=self.delete_memory_category,
                aliases=['del-mem-cat', 'remove-memory-category']
            )
        )
        
        ################## CONNECTIONS ################## 
        # List actions command
        self._register_command(
            Command(
                name="list-actions",
                description="Lists all available actions for the given connection.",
                tips=["Format: list-actions {connection}",
                      "Use 'list-connections' to see available connections"],
                handler=self.list_actions,
                aliases=['actions', 'ls-actions']
            )
        )
        
        # Configure connection command
        self._register_command(
            Command(
                name="configure-connection",
                description="Sets up a connection for API access.",
                tips=["Format: configure-connection {connection}",
                      "Follow the prompts to enter necessary credentials"],
                handler=self.configure_connection,
                aliases=['config', 'setup']
            )
        )
        
        # List connections command
        self._register_command(
            Command(
                name="list-connections",
                description="Lists all available connections.",
                tips=["Shows both configured and unconfigured connections"],
                handler=self.list_connections,
                aliases=['connections', 'ls-connections']
            )
        )
        
        ################## MISC ################## 
        # Exit command
        self._register_command(
            Command(
                name="exit",
                description="Exits the ZerePy CLI.",
                tips=["You can also use Ctrl+D to exit"],
                handler=self.exit,
                aliases=['quit', 'q']
            )
        )

    def _setup_prompt_toolkit(self) -> None:
        """Setup prompt toolkit components"""
        self.style = Style.from_dict({
            'prompt': 'ansicyan bold',
            'command': 'ansigreen',
            'error': 'ansired bold',
            'success': 'ansigreen bold',
            'warning': 'ansiyellow',
        })

        # Use FileHistory for persistent command history
        history_file = self.config_dir / 'history.txt'
        
        self.completer = WordCompleter(
            list(self.commands.keys()), 
            ignore_case=True,
            sentence=True
        )
        
        self.session = PromptSession(
            completer=self.completer,
            style=self.style,
            history=FileHistory(str(history_file))
        )

    ###################
    # Helper Functions
    ###################
    def _register_command(self, command: Command) -> None:
        """Register a command and its aliases"""
        self.commands[command.name] = command
        for alias in command.aliases:
            self.commands[alias] = command

    def _get_prompt_message(self) -> HTML:
        """Generate the prompt message based on current state"""
        agent_status = f"({self.agent.name})" if self.agent else "(no agent)"
        return HTML(f'<prompt>ZerePy-CLI</prompt> {agent_status} > ')

    def _handle_command(self, input_string: str) -> None:
        """Parse and handle a command input"""
        input_list = input_string.split()
        command_string = input_list[0].lower()

        try:
            command = self.commands.get(command_string)
            if command:
                command.handler(input_list)
            else:
                self._handle_unknown_command(command_string)
        except Exception as e:
            logger.error(f"Error executing command: {e}")

    def _handle_unknown_command(self, command: str) -> None:
        """Handle unknown command with suggestions"""
        logger.warning(f"Unknown command: '{command}'") 

        # Suggest similar commands using basic string similarity
        suggestions = self._get_command_suggestions(command)
        if suggestions:
            logger.info("Did you mean one of these?")
            for suggestion in suggestions:
                logger.info(f"  - {suggestion}")
        logger.info("Use 'help' to see all available commands.")

    def _get_command_suggestions(self, command: str, max_suggestions: int = 3) -> List[str]:
        """Get command suggestions based on string similarity"""
        from difflib import get_close_matches
        return get_close_matches(command, self.commands.keys(), n=max_suggestions, cutoff=0.6)

    def _print_welcome_message(self, clearing: bool = False) -> None:
        """Print welcome message and initial status
        
        Args:
            clearing (bool): Whether this is being called during a screen clear
                        When True, skips the final horizontal bar to avoid doubles
        """
        print_h_bar()
        logger.info("👋 Welcome to the ZerePy CLI!")
        logger.info("Type 'help' for a list of commands.")
        if not clearing:
            print_h_bar()

    def _show_command_help(self, command_name: str) -> None:
        """Show help for a specific command"""
        command = self.commands.get(command_name)
        if not command:
            logger.warning(f"Unknown command: '{command_name}'")
            suggestions = self._get_command_suggestions(command_name)
            if suggestions:
                logger.info("Did you mean one of these?")
                for suggestion in suggestions:
                    logger.info(f"  - {suggestion}")
            return

        logger.info(f"\nHelp for '{command.name}':")
        logger.info(f"Description: {command.description}")
        
        if command.aliases:
            logger.info(f"Aliases: {', '.join(command.aliases)}")
        
        if command.tips:
            logger.info("\nTips:")
            for tip in command.tips:
                logger.info(f"  - {tip}")

    def _show_general_help(self) -> None:
        """Show general help information"""
        logger.info("\nAvailable Commands:")
        # Group commands by first letter for better organization
        commands_by_letter = {}
        for cmd_name, cmd in self.commands.items():
            # Only show main commands, not aliases
            if cmd_name == cmd.name:
                first_letter = cmd_name[0].upper()
                if first_letter not in commands_by_letter:
                    commands_by_letter[first_letter] = []
                commands_by_letter[first_letter].append(cmd)

        for letter in sorted(commands_by_letter.keys()):
            logger.info(f"\n{letter}:")
            for cmd in sorted(commands_by_letter[letter], key=lambda x: x.name):
                logger.info(f"  {cmd.name:<15} - {cmd.description}")

    def _list_loaded_agent(self) -> None:
        if self.agent:
            logger.info(f"\nStart the agent loop with the command 'start' or use one of the action commands.")
        else:
            logger.info(f"\nNo default agent is loaded, please use the load-agent command to do that.")

    def _load_agent_from_file(self, agent_name):
        try: 
            self.agent = ZerePyAgent(agent_name)
            logger.info(f"\n✅ Successfully loaded agent: {self.agent.name}")
        except FileNotFoundError:
            logger.error(f"Agent file not found: {agent_name}")
            logger.info("Use 'list-agents' to see available agents.")
        except KeyError as e:
            logger.error(f"Invalid agent file: {e}")
        except Exception as e:
            logger.error(f"Error loading agent: {e}")

    def _load_default_agent(self) -> None:
        """Load users default agent"""
        agent_general_config_path = Path("agents") / "general.json"
        file = None
        try:
            file = open(agent_general_config_path, 'r')
            data = json.load(file)
            if not data.get('default_agent'):
                logger.error('No default agent defined, please set one in general.json')
                return

            self._load_agent_from_file(data.get('default_agent'))
        except FileNotFoundError:
            logger.error("File general.json not found, please create one.")
            return
        except json.JSONDecodeError:
            logger.error("File agents/general.json contains Invalid JSON format")
            return
        finally:
            if file:
                file.close()
    
    ###################
    # Command functions
    ###################
    def help(self, input_list: List[str]) -> None:
        """List all commands supported by the CLI"""
        if len(input_list) > 1:
            self._show_command_help(input_list[1])
        else:
            self._show_general_help()

    def clear_screen(self, input_list: List[str]) -> None:
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        self._print_welcome_message(clearing=True)

    def agent_action(self, input_list: List[str]) -> None:
        """Handle agent action command"""
        if self.agent is None:
            logger.info("No agent is currently loaded. Use 'load-agent' to load an agent.")
            return

        if len(input_list) < 3:
            logger.info("Please specify both a connection and an action.")
            logger.info("Format: agent-action {connection} {action}")
            return

        try:
            result = self.agent.perform_action(
                connection=input_list[1],
                action=input_list[2],
                params=input_list[3:]
            )
            logger.info(f"Result: {result}")
        except Exception as e:
            logger.error(f"Error running action: {e}")

    def agent_loop(self, input_list: List[str]) -> None:
        """Handle agent loop command"""
        if self.agent is None:
            logger.info("No agent is currently loaded. Use 'load-agent' to load an agent.")
            return

        try:
            self.agent.loop()
        except KeyboardInterrupt:
            logger.info("\n🛑 Agent loop stopped by user.")
        except Exception as e:
            logger.error(f"Error in agent loop: {e}")

    def list_agents(self, input_list: List[str]) -> None:
        """Handle list agents command"""
        logger.info("\nAvailable Agents:")
        agents_dir = Path("agents")
        if not agents_dir.exists():
            logger.info("No agents directory found.")
            return

        agents = list(agents_dir.glob("*.json"))
        if not agents:
            logger.info("No agents found. Use 'create-agent' to create a new agent.")
            return

        for agent_file in sorted(agents):
            if agent_file.stem == "general":
                continue
            logger.info(f"- {agent_file.stem}")

    def load_agent(self, input_list: List[str]) -> None:
        """Handle load agent command"""
        if len(input_list) < 2:
            logger.info("Please specify an agent name.")
            logger.info("Format: load-agent {agent_name}")
            logger.info("Use 'list-agents' to see available agents.")
            return

        self._load_agent_from_file(agent_name=input_list[1])
    
    def create_agent(self, input_list: List[str]) -> None:
        """Handle create agent command"""
        logger.info("\nℹ️ Agent creation wizard not implemented yet.")
        logger.info("Please create agent JSON files manually in the 'agents' directory.")
    
    def set_default_agent(self, input_list: List[str]):
        """Handle set-default-agent command"""
        if len(input_list) < 2:
            logger.info("Please specify the same of the agent file.")
            return
        
        agent_general_config_path = Path("agents") / "general.json"
        file = None
        try:
            file = open(agent_general_config_path, 'r')
            data = json.load(file)
            agent_file_name = input_list[1]
            # if file does not exist, refuse to set it as default
            try:
                agent_path = Path("agents") / f"{agent_file_name}.json"
                open(agent_path, 'r')
            except FileNotFoundError:
                logging.error("Agent file not found.")
                return
            
            data['default_agent'] = input_list[1]
            with open(agent_general_config_path, 'w') as f:
                json.dump(data, f, indent=4)
            logger.info(f"Agent {agent_file_name} is now set as default.")
        except FileNotFoundError:
            logger.error("File not found")
            return
        except json.JSONDecodeError:
            logger.error("Invalid JSON format")
            return
        finally:
            if file:
                file.close()

    def list_actions(self, input_list: List[str]) -> None:
        """Handle list actions command"""
        if len(input_list) < 2:
            logger.info("\nPlease specify a connection.")
            logger.info("Format: list-actions {connection}")
            logger.info("Use 'list-connections' to see available connections.")
            return

        self.agent.connection_manager.list_actions(connection_name=input_list[1])

    def configure_connection(self, input_list: List[str]) -> None:
        """Handle configure connection command"""
        if len(input_list) < 2:
            logger.info("\nPlease specify a connection to configure.")
            logger.info("Format: configure-connection {connection}")
            logger.info("Use 'list-connections' to see available connections.")
            return

        self.agent.connection_manager.configure_connection(connection_name=input_list[1])

    def list_connections(self, input_list: List[str] = []) -> None:
        """Handle list connections command"""
        if self.agent:
            self.agent.connection_manager.list_connections()
        else:
            logging.info("Please load an agent to see the list of supported actions")

    def chat_session(self, input_list: List[str]) -> None:
        """Handle chat command"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return

        if not self.agent.is_llm_set:
            self.agent._setup_llm_provider()

        logger.info(f"\nStarting chat with {self.agent.name}")
        print_h_bar()

        while True:
            try:
                user_input = self.session.prompt("\nYou: ").strip()
                if user_input.lower() == 'exit':
                    break

                # Search relevant memories before responding
                relevant_memories = self.agent.memory.search(
                    category="reference_materials",
                    query=user_input,
                    n_results=3
                )

                # Construct context from memories
                memory_context = ""
                if relevant_memories:
                    memory_context = "\nRelevant information from my memory:\n"
                    for result in relevant_memories:
                        memory_context += f"- {result.memory.content}\n"

                # Add memory context to prompt
                enriched_prompt = f"{user_input}\n{memory_context}"
                
                response = self.agent.prompt_llm(enriched_prompt)

                # Store the interaction in memory
                self.agent.memory.create(
                    category="conversations",
                    content=f"User: {user_input}\nAgent: {response}",
                    metadata={
                        "type": "chat",
                        "role": "human",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                logger.info(f"\n{self.agent.name}: {response}")
                print_h_bar()
                
            except KeyboardInterrupt:
                break

    def upload_document(self, input_list: List[str]) -> None:
        """Handle document upload to memory"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
            
        if len(input_list) < 3:
            logger.info("Please specify both a file path and category.")
            logger.info("Format: upload-document {filepath} {category}")
            return
            
        filepath = input_list[1]
        category = input_list[2]
        
        try:
            # Get file extension
            file_ext = Path(filepath).suffix.lower()
            
            if file_ext == '.pdf':
                memory_ids = self.agent.memory.ingest_pdf(
                    filepath,
                    category=category,
                    metadata={
                        "source": filepath,
                        "type": "document",
                        "format": "pdf"
                    }
                )
                logger.info(f"✅ Successfully stored PDF in {len(memory_ids)} chunks")
                
            elif file_ext in ['.txt', '.md']:
                with open(filepath, 'r', encoding='utf-8') as file:
                    content = file.read()
                    memory_id = self.agent.memory.create(
                        category=category,
                        content=content,
                        metadata={
                            "source": filepath,
                            "type": "document",
                            "format": file_ext[1:]  # remove the dot
                        }
                    )
                    logger.info(f"✅ Successfully stored text document")
            else:
                logger.error(f"Unsupported file format: {file_ext}")
                
        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
        except Exception as e:
            logger.error(f"Error uploading document: {e}")

    def search_memory(self, input_list: List[str]) -> None:
        """Search agent's memory"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
            
        if len(input_list) < 3:
            logger.info("Please specify both a category and search query.")
            logger.info("Format: search-memory {category} {query}")
            return
            
        category = input_list[1]
        # Combine remaining words as the query
        query = " ".join(input_list[2:])
        
        try:
            results = self.agent.memory.search(
                category=category,
                query=query,
                n_results=5
            )
            
            if not results:
                logger.info(f"No memories found in category '{category}' matching '{query}'")
                return
                
            logger.info(f"\nFound {len(results)} relevant memories:")
            print_h_bar()
            
            for i, result in enumerate(results, 1):
                memory = result.memory
                similarity = result.similarity_score
                
                logger.info(f"\n{i}. Similarity: {similarity:.2f}")
                logger.info(f"Category: {memory.category}")
                logger.info(f"Content: {memory.content[:200]}...")  # Show first 200 chars
                logger.info(f"Metadata: {memory.metadata}")
                print_h_bar()
                
        except Exception as e:
            logger.error(f"Error searching memories: {e}")

    def list_memory_categories(self, input_list: List[str]) -> None:
        """List all memory categories"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
        
        try:
            categories = self.agent.memory.list_categories()
            
            if not categories:
                logger.info("No memory categories found.")
                return
                
            logger.info("\nMemory Categories:")
            for category in categories:
                count = self.agent.memory.count(category)
                logger.info(f"- {category} ({count} memories)")
                
        except Exception as e:
            logger.error(f"Error listing categories: {e}")

    def delete_memory_category(self, input_list: List[str]) -> None:
        """Delete all memories in a category"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
            
        if len(input_list) < 2:
            logger.info("Please specify a category to delete.")
            logger.info("Format: delete-memory-category {category}")
            return
            
        category = input_list[1]

        # Check if category exists first
        if category not in self.agent.memory.list_categories():
            logger.error(f"Category '{category}' does not exist.")
            logger.info("Use 'list-memory-categories' to see available categories.")
            return
        
        try:
            self.agent.memory.delete_category(category)
            logger.info(f"✅ Successfully deleted category: {category}")
        except Exception as e:
            logger.error(f"Error deleting memory category: {e}")

    def exit(self, input_list: List[str]) -> None:
        """Exit the CLI gracefully"""
        logger.info("\nGoodbye! 👋")
        sys.exit(0)


    ###################
    # Main CLI Loop
    ###################
    def main_loop(self) -> None:
        """Main CLI loop"""
        self._print_welcome_message()
        self._load_default_agent()
        self._list_loaded_agent()
        self.list_connections()
        
        # Start CLI loop
        while True:
            try:
                input_string = self.session.prompt(
                    self._get_prompt_message(),
                    style=self.style
                ).strip()

                if not input_string:
                    continue

                self._handle_command(input_string)
                print_h_bar()

            except KeyboardInterrupt:
                continue
            except EOFError:
                self.exit([])
            except Exception as e:
                logger.exception(f"Unexpected error: {e}") 