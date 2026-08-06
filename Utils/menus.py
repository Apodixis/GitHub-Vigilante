import sys, subprocess, os

def quitProgram() -> None:
    """
    Pauses execution to provide a user the opportunity to read any error messages before exiting the program.
    """
    input("Press enter to exit...")
    sys.exit(1)

def clearTerminal() -> None:
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