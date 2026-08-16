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
    Returns the inputs as a set of unique strings.
    """
    targets: set[str] = set()
    print(f"Enter {target_type} login values")
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

def user_search_mode() -> str:
    # Menu for selecting user search mode when running main.py
    clear_terminal()
    print("1) User Search - Exact Match") # Finds information for a specific user: (User, Followership, and Stargazing)
    print("2) User Search - Partial Match") #Finds users based on partial matches (will likely return multiple results)
    
    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice == "1" or choice == "2":
            return choice
        else:
            print("Invalid selection. Please enter 1 or 2.")

def organization_search_mode() -> str:
    # Menu for selecting organization search mode when running main.py
    clear_terminal()
    print("1) Organization Search - Exact Match") # Finds information for a specific organization and its members
    print("2) Organization Search - Membership Intersect") # Finds users who are members of multiple organizations
    
    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice == "1" or choice == "2":
            return choice
        else:
            print("Invalid selection. Please enter 1 or 2.")