# Copyright (C) 2010-2015 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import os
import shutil

from lib.common.abstracts import Package

class CAPE_Extraction(Package):
    """CAPE Extraction analysis package."""
    #PATHS = [
    #    ("SystemRoot", "system32"),
    #]

    def __init__(self, options={}, config=None):
        """@param options: options dict."""
        self.config = config
        self.options = options
        self.pids = []
        self.options["dll"] = "CAPE_Extraction.dll"
        self.options["procmemdump"] = '0'

    def start(self, path):
        self.options["dll"] = "CAPE_Extraction.dll"
        self.options["procmemdump"] = '0'
        arguments = self.options.get("arguments")
        
        # If the file doesn't have an extension, add .exe
        # See CWinApp::SetCurrentHandles(), it will throw
        # an exception that will crash the app if it does
        # not find an extension on the main exe's filename
        if "." not in os.path.basename(path):
            new_path = path + ".exe"
            os.rename(path, new_path)
            path = new_path
        
        return self.debug(path, arguments, path)
