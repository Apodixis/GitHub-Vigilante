import sys, subprocess, os

def quit_program() -> None:
    """
    Pauses execution to provide a user the opportunity to read any error messages before exiting the program.
    """
    input("Press enter to exit...")
    sys.exit(1)

def clear_terminal() -> None:
    """
    Clears the terminal screen. Improves readability of the program's outputs and enables
    the use of execution progress updates in the terminal (important for longer execution time functions).
    """
    try:
        print("\033[2J\033[H", end="")  # ANSI escape codes to clear the terminal screen and move the cursor to the top-left corner]]")
    except Exception as e:
        print(f"Error clearing terminal: {e}. Attempting to use OS-specific command instead.")
        input("Press enter to continue...")
        command = 'cls' if os.name == 'nt' else 'clear'
        subprocess.run(command, shell=True)

def multiple_input_prompt(target_type: str) -> set[str]:
    """
    Prompts the user for multiple inputs of a specified target type.
    Input: String specifying target type (used to alter user input prompt)
    Output: Set of one or more unique inputs for use in the selected search method
    """
    targets: set[str] = set()
    print(f"Enter {target_type} values")
    print("Press Enter on an empty line when finished.")
    while True:
        raw_input_value = input(f"{target_type}(s): ").strip()
        if not raw_input_value:
            if targets:
                clear_terminal()
                break
            print(f"At least one {target_type} is required.")
            continue
        
        parsed_values = [value for value in raw_input_value.replace(",", " ").split() if value]
        for value in parsed_values:
            targets.add(value)
    
    clear_terminal()
    return targets

def selection_menu(options: list[str]) -> str:
    """
    Menu for selecting an option from a provided list when running main.py
    Inputs: List of options to display in the menus
    Output: Returns the user's choice as a string ("1", "2", ..., "n") corresponding to the selected option
    """
    clear_terminal()
    # prints each option with its corresponding number
    for i, option in enumerate(options, start=1):
        print(f"{i}) {option}")
    
    while True:
        choice = input(f"Enter a number between 1 and {len(options)}: ").strip()
        if choice in map(str, range(1, len(options) + 1)):
            return choice
        else:
            print(f"Invalid selection. Please enter a number between 1 and {len(options)}.")

def recursion_menu(minimum: int = 0, maximum: int = 3) -> str:
    """
    Menu for specifying how many recursions to perform (depth) in the search
    Inputs: None
    Output: Returns the user's choice as a string ("0", "1", ..., "n") corresponding to the selected recursion depth
    """
    clear_terminal()
    
    while True:
        raw_input_value = input(f"Specify desired depth (number of layers of information). Enter a number between {minimum} and {maximum}: ").strip()
        try:
            input_value = float(raw_input_value)
            depth = int(-(-input_value // 1)) # handles float value inputs by rounding up to the nearest integer
            return max(minimum, min(depth, maximum)) # clamps value to (minimum, maximum) range
        
        except ValueError:
            print(f"Invalid selection. Please enter a number between {minimum} and {maximum}.")