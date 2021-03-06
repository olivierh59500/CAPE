# Copyright (C) 2010-2015 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import os
import shutil

from lib.common.abstracts import Package

class CAPE_Extraction_Regsvr(Package):
    """CAPE Extraction DLL analysis package."""
    PATHS = [
        ("SystemRoot", "system32", "regsvr32.exe"),
    ]

    def __init__(self, options={}, config=None):
        """@param options: options dict."""
        self.config = config
        self.options = options
        self.options["dll"] = "CAPE_Extraction.dll"
        #self.options["dll_64"] = "CAPE_Extraction_x64.dll"

    def start(self, path):
        regsvr32 = self.get_path("regsvr32.exe")
        arguments = self.options.get("arguments")

        # Check file extension.
        ext = os.path.splitext(path)[-1].lower()
        # If the file doesn't have the proper .dll extension force it
        # and rename it. This is needed for rundll32 to execute correctly.
        # See ticket #354 for details.
        if ext != ".dll":
            new_path = path + ".dll"
            os.rename(path, new_path)
            path = new_path

        args = path
        if arguments:
            args += " {0}".format(arguments)

        return self.debug(regsvr32, args, path)
