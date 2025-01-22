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
                name="memory-upload",
                description="Upload one or more documents to the agent's memory",
                tips=["Format: memory-upload {category} file1 [file2 file3 ...]",
                    "All files will be stored in the same category",
                    "You can use wildcards like notes/*.txt to upload all text files in the notes folder"],
                handler=self.memory_upload,
                aliases=['mem-upload']
            )
        )

        self._register_command(
            Command(
                name="memory-list",
                description="List memory categories or documents within a category",
                tips=["Format: memory-list [category]",
                    "Without category: shows all categories and their sizes",
                    "With category: shows documents in that category"],
                handler=self.memory_list,
                aliases=['mem-list']
            )
        )

        self._register_command(
            Command(
                name="memory-search",
                description="Search all memories or within a specific category",
                tips=["Format: memory-search 'search terms' [category]",
                    "Example: memory-search 'blockchain basics'",
                    "Example: memory-search 'smart contracts' solana"],
                handler=self.memory_search,
                aliases=['mem-search']
            )
        )

        self._register_command(
            Command(
                name="memory-wipe",
                description="Delete memories at different levels (all, category, or document)",
                tips=["Format: memory-wipe [category] [filename]",
                    "Without arguments: wipes all memories",
                    "With category: wipes entire category",
                    "With category and filename: wipes specific document"],
                handler=self.memory_wipe,
                aliases=['mem-wipe']
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
                
                memory_context = ""
                if len(user_input.split()) > 3:  # Basic check for query complexity
                    logger.info("\n🔍 Searching memories...")

                    available_categories = self.agent.memory.list_categories()
                    
                    relevant_memories = self.agent.memory.search(
                        category=available_categories,
                        query=user_input,
                        n_results=3,
                        min_similarity=0.2
                    )
                    
                    if relevant_memories:
                        logger.info("Found relevant memories:")
                        for i, result in enumerate(relevant_memories, 1):
                            logger.info(f"Memory {i} (similarity: {result.similarity_score:.2f}):")
                            logger.info(f"  {result.memory.content[:100]}...")
                            memory_context += f"From {result.memory.metadata.get('source', 'reference')}:\n{result.memory.content}\n\n"

                # Construct final prompt
                enriched_prompt = (
                    f"{user_input}\n\n"
                    f"{'Knowledge to draw from:\n' + memory_context if memory_context else ''}"
                    f"Use your personality and style to respond, incorporating any relevant knowledge naturally."
                )
                
                response = self.agent.prompt_llm(enriched_prompt)
                logger.info(f"\n{self.agent.name}: {response}")
                print_h_bar()
                    
            except KeyboardInterrupt:
                break

    def memory_upload(self, input_list: List[str]) -> None:
        """Handle document upload to memory"""
        if not self.agent:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
                
        if len(input_list) < 3:
            logger.info("Please specify a category and at least one file.")
            logger.info("Format: memory-upload {category} file1 [file2 file3 ...]")
            return
                
        category = input_list[1]
        filepaths = input_list[2:]
        
        # Expand any wildcards in filepaths
        import glob
        expanded_paths = []
        for filepath in filepaths:
            expanded = glob.glob(filepath)
            if expanded:
                expanded_paths.extend(expanded)
            else:
                expanded_paths.append(filepath)  # Keep original path if no matches
        
        if not expanded_paths:
            logger.info("No matching files found.")
            return
        
        successful = 0
        failed = 0
        total_chunks = 0
        
        for filepath in expanded_paths:
            try:
                memory_ids = self.agent.memory.create_chunks(
                    filepath,
                    category=category,
                    metadata={
                        "type": "document",
                        "original_filename": filepath,
                        "upload_timestamp": datetime.now().isoformat()
                    }
                )
                successful += 1
                total_chunks += len(memory_ids)
                logger.info(f"✅ Successfully processed: {filepath} ({len(memory_ids)} chunks)")
                        
            except FileNotFoundError:
                logger.error(f"❌ File not found: {filepath}")
                failed += 1
            except Exception as e:
                logger.error(f"❌ Error processing {filepath}: {e}")
                failed += 1
        
        # Summary
        logger.info("\nUpload Summary:")
        logger.info(f"Total files attempted: {len(expanded_paths)}")
        logger.info(f"Successfully processed: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total chunks created: {total_chunks}")

    def memory_list(self, input_list: List[str]) -> None:
        """List memory categories or documents in a category"""
        if not self.agent:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
        
        # If no category specified, list all categories
        if len(input_list) < 2:
            categories = self.agent.memory.list_categories()
            
            if not categories:
                logger.info("No memory categories found.")
                return
                
            print_h_bar()
            
            for category in sorted(categories):
                count = self.agent.memory.count(category)
                memories = self.agent.memory.get_recent(category, n_results=1000)
                
                # Count unique documents by filename
                unique_docs = len(set(mem.metadata.get('original_filename', 'Unknown') 
                                for mem in memories))
                
                logger.info(f"\nCategory: {category}")
                logger.info(f"Documents: {unique_docs}")
                logger.info(f"Total chunks: {count}")
            
            print_h_bar()
            return
                
        # Otherwise, list documents in the specified category
        category = input_list[1]
        
        try:
            memories = self.agent.memory.get_recent(category, n_results=1000)
            
            if not memories:
                logger.info(f"No documents found in category '{category}'")
                return
                
            # Group memories by original filename
            from collections import defaultdict
            docs = defaultdict(list)
            for memory in memories:
                filename = memory.metadata.get('original_filename', 'Unknown source')
                docs[filename].append(memory)
            
            logger.info(f"\nDocuments in category '{category}':")
            print_h_bar()
            
            for filename, chunks in docs.items():
                total_size = sum(len(chunk.content) for chunk in chunks)
                logger.info(f"\nFile: {filename}")
                logger.info(f"Chunks: {len(chunks)}")
                logger.info(f"Total size: {total_size:,} characters")
                logger.info(f"Upload date: {chunks[0].metadata.get('upload_timestamp', 'Unknown')[:10]}")
                
            print_h_bar()
            
        except Exception as e:
            logger.error(f"Error listing memories: {e}")

    def memory_search(self, input_list: List[str]) -> None:
        """Search memories across all or specific categories"""
        if not self.agent:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return
                
        if len(input_list) < 2:
            logger.info("Please specify a search query.")
            logger.info("Format: memory-search query [category]")
            return
        
        # Get query and optional category
        query = input_list[1]
        category = input_list[2] if len(input_list) > 2 else None
        categories = [category] if category else self.agent.memory.list_categories()
        
        try:
            results = self.agent.memory.search(
                category=categories,
                query=query,
                n_results=5,
                min_similarity=0.1
            )
            
            if not results:
                if category:
                    logger.info(f"No results found in category '{category}' for '{query}'")
                else:
                    logger.info(f"No results found for '{query}'")
                return
            
            logger.info(f"\nSearch results for '{query}':")
            print_h_bar()
            
            for i, result in enumerate(results, 1):
                memory = result.memory
                similarity = result.similarity_score
                
                logger.info(f"\n{i}. Match strength: {similarity:.2f}")
                logger.info(f"Category: {memory.category}")
                logger.info(f"From: {memory.metadata.get('original_filename', 'Unknown source')}")
                logger.info(f"Content: {memory.content[:200]}...")  # Show first 200 chars
                
            print_h_bar()
                
        except Exception as e:
            logger.error(f"Error searching memories: {e}")

    def memory_wipe(self, input_list: List[str]) -> None:
        """Wipe memories at different levels"""
        if not self.agent:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return

        # Wipe everything
        if len(input_list) == 1:
            categories = self.agent.memory.list_categories()
            if not categories:
                logger.info("No memories to wipe.")
                return
                
            logger.info("\n⚠️  WARNING: This will delete ALL memories for this agent!")
            logger.info(f"Categories to be wiped: {', '.join(categories)}")
            
            confirmation = self.session.prompt("\nType 'yes' to confirm: ").strip().lower()
            if confirmation != 'yes':
                logger.info("Operation cancelled.")
                return
                
            import shutil
            try:
                # Get the agent-specific memory path from store's db_path
                memory_path = self.agent.memory.store.db_path
                logger.info(f"Wiping memories at: {memory_path}")
                shutil.rmtree(memory_path)
                self.agent.memory.store.collections.clear()
                logger.info("✅ All memories wiped successfully.")
            except Exception as e:
                logger.error(f"Error wiping memories: {e}")
            return

        # Wipe category
        category = input_list[1]
        if len(input_list) == 2:
            try:
                count = self.agent.memory.count(category)
                if count == 0:
                    logger.info(f"No memories found in category '{category}'")
                    return
                    
                logger.info(f"\n⚠️  WARNING: This will delete all memories in category '{category}'")
                logger.info(f"Documents to be wiped: {count} chunks")
                
                confirmation = self.session.prompt("\nType 'yes' to confirm: ").strip().lower()
                if confirmation != 'yes':
                    logger.info("Operation cancelled.")
                    return
                    
                self.agent.memory.delete_category(category)
                logger.info(f"✅ Category '{category}' wiped successfully.")
            except Exception as e:
                logger.error(f"Error wiping category: {e}")
            return

        # Wipe specific document
        filename = input_list[2]
        try:
            memories = self.agent.memory.get_recent(category, n_results=1000)
            chunks_to_delete = [
                mem for mem in memories 
                if mem.metadata.get('original_filename') == filename
            ]
            
            if not chunks_to_delete:
                logger.info(f"No document found matching '{filename}' in category '{category}'")
                return
                
            logger.info(f"\n⚠️  WARNING: This will delete '{filename}' from category '{category}'")
            logger.info(f"Chunks to be wiped: {len(chunks_to_delete)}")
            
            confirmation = self.session.prompt("\nType 'yes' to confirm: ").strip().lower()
            if confirmation != 'yes':
                logger.info("Operation cancelled.")
                return
                
            for chunk in chunks_to_delete:
                self.agent.memory.delete(category, chunk.id)
            
            logger.info(f"✅ Document '{filename}' wiped successfully from '{category}'")
        except Exception as e:
            logger.error(f"Error wiping document: {e}")

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