class CodeBuilder(object):
    """ Build source code """
    
    def __init__(self, indent=0):
        self.code = []
        self.indent_level = indent
    
    def add_line(self, line):
        """Add a line of source to the code.

        Indentation and newline will be added for you, don't provide them.

        """
        self.code.extend([" " * self.indent_level, line, "\n"])
    
    INDENT_STEP = 4
    def indent(self):
        """Increase the current indent for following lines."""
        #print("indent is", self.indent_level)
        self.indent_level += self.INDENT_STEP

    def dedent(self):
        """Decrease the current indent for following lines."""
        #print("indent is", self.indent_level)
        self.indent_level -= self.INDENT_STEP
        
    def add_section(self):
        """Add a section, a sub-CodeBuilder."""
        section = CodeBuilder(self.indent_level)
        self.code.append(section)
        return section
    
    def __str__(self):
        return "".join(str(c) for c in self.code)
    
    def get_globals(self):
        """Execute the code, and return a dict of globals it defines."""
        # A check that the caller really finished all the blocks they started.
        assert self.indent_level == 0
        # Get the Python source as a single string.
        python_source = str(self)
        # Execute the source, defining globals, and return them.
        global_namespace = {}
        print(" this is python src",python_source)
        exec(python_source, global_namespace)
        return global_namespace