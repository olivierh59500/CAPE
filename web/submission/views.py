# Copyright (C) 2010-2015 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import os
import sys

import requests
import tempfile
import random

try:
    import re2 as re
except ImportError:
    import re

from django.conf import settings
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required

sys.path.append(settings.CUCKOO_PATH)

from lib.cuckoo.common.config import Config
from lib.cuckoo.common.utils import store_temp_file, validate_referrer
from lib.cuckoo.common.quarantine import unquarantine
from lib.cuckoo.common.saztopcap import saz_to_pcap
from lib.cuckoo.common.exceptions import CuckooDemuxError
from lib.cuckoo.core.database import Database

# Conditional decorator for web authentication
class conditional_login_required(object):
    def __init__(self, dec, condition):
        self.decorator = dec
        self.condition = condition
    def __call__(self, func):
        if not self.condition:
            return func
        return self.decorator(func)

def force_int(value):
    try:
        value = int(value)
    except:
        value = 0
    finally:
        return value

def update_options(gw, orig_options):
    options = orig_options
    if gw:
        if orig_options:
            options = orig_options + ",setgw=%s" % (gw)
        else:
            options = "setgw=%s" % (gw)
        if settings.GATEWAYS_IP_MAP.has_key(gw) and settings.GATEWAYS_IP_MAP[gw]:
            options += ",gwname=%s" % (settings.GATEWAYS_IP_MAP[gw])

    return options

@conditional_login_required(login_required, settings.WEB_AUTHENTICATION)
def index(request):
    if request.method == "POST":
        package = request.POST.get("package", "")
        timeout = min(force_int(request.POST.get("timeout")), 60 * 60 * 24)
        options = request.POST.get("options", "")
        priority = force_int(request.POST.get("priority"))
        machine = request.POST.get("machine", "")
        gateway = request.POST.get("gateway", None)
        clock = request.POST.get("clock", None)
        custom = request.POST.get("custom", "")
        memory = bool(request.POST.get("memory", False))
        enforce_timeout = bool(request.POST.get("enforce_timeout", False))
        referrer = validate_referrer(request.POST.get("referrer", None))
        tags = request.POST.get("tags", None)

        task_gateways = []
        ipaddy_re = re.compile(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")

        if referrer:
            if options:
                options += ","
            options += "referrer=%s" % (referrer)

        if request.POST.get("free"):
            if options:
                options += ","
            options += "free=yes"

        if request.POST.get("nohuman"):
            if options:
                options += ","
            options += "nohuman=yes"

        if request.POST.get("tor"):
            if options:
                options += ","
            options += "tor=yes"

        if request.POST.get("process_memory"):
            if options:
                options += ","
            options += "procmemdump=0"
        else:
            if options:
                options += ","
            options += "procmemdump=1"
        
        if request.POST.get("import_reconstruction"):
            if options:
                options += ","
            options += "import_reconstruction=1"

        if request.POST.get("kernel_analysis"):
            if options:
                options += ","
            options += "kernel_analysis=yes"   

        if request.POST.get("norefer"):
            if options:
                options += ","
            options += "norefer=1"

        orig_options = options

        if gateway and gateway.lower() == "all":
            for e in settings.GATEWAYS:
                if ipaddy_re.match(settings.GATEWAYS[e]):
                    task_gateways.append(settings.GATEWAYS[e])
        elif gateway and gateway in settings.GATEWAYS:
            if "," in settings.GATEWAYS[gateway]:
                if request.POST.get("all_gw_in_group"):
                    tgateway = settings.GATEWAYS[gateway].split(",")
                    for e in tgateway:
                        task_gateways.append(settings.GATEWAYS[e]) 
                else:
                    tgateway = random.choice(settings.GATEWAYS[gateway].split(","))
                    task_gateways.append(settings.GATEWAYS[tgateway])
            else:
                task_gateways.append(settings.GATEWAYS[gateway])

        if not task_gateways:
            # To reduce to the default case
            task_gateways = [None]

        db = Database()
        task_ids = []
        task_machines = []

        if machine.lower() == "all":
            for entry in db.list_machines():
                task_machines.append(entry.label)
        else:
            task_machines.append(machine)

        if "sample" in request.FILES:
            samples = request.FILES.getlist("sample")
            for sample in samples:
                # Error if there was only one submitted sample and it's empty.
                # But if there are multiple and one was empty, just ignore it.
                if not sample.size:
                    if len(samples) != 1:
                        continue

                    return render(request, "error.html",
                                              {"error": "You uploaded an empty file."})
                elif sample.size > settings.MAX_UPLOAD_SIZE:
                    return render(request, "error.html",
                                              {"error": "You uploaded a file that exceeds the maximum allowed upload size specified in web/web/local_settings.py."})
    
                # Moving sample from django temporary file to Cuckoo temporary storage to
                # let it persist between reboot (if user like to configure it in that way).
                path = store_temp_file(sample.read(),
                                       sample.name)
    
                for gw in task_gateways:
                    options = update_options(gw, orig_options)

                    for entry in task_machines:
                        try:
                            task_ids_new = db.demux_sample_and_add_to_db(file_path=path, package=package, timeout=timeout, options=options, priority=priority,
                                    machine=entry, custom=custom, memory=memory, enforce_timeout=enforce_timeout, tags=tags, clock=clock)
                            task_ids.extend(task_ids_new)
                        except CuckooDemuxError as err:
                            return render(request, "error.html", {"error": err})

        elif "quarantine" in request.FILES:
            samples = request.FILES.getlist("quarantine")
            for sample in samples:
                # Error if there was only one submitted sample and it's empty.
                # But if there are multiple and one was empty, just ignore it.
                if not sample.size:
                    if len(samples) != 1:
                        continue

                    return render(request, "error.html",
                                              {"error": "You uploaded an empty quarantine file."})
                elif sample.size > settings.MAX_UPLOAD_SIZE:
                    return render(request, "error.html",
                                              {"error": "You uploaded a quarantine file that exceeds the maximum allowed upload size specified in web/web/local_settings.py."})
    
                # Moving sample from django temporary file to Cuckoo temporary storage to
                # let it persist between reboot (if user like to configure it in that way).
                tmp_path = store_temp_file(sample.read(),
                                       sample.name)

                path = unquarantine(tmp_path)
                try:
                    os.remove(tmp_path)
                except:
                    pass

                if not path:
                    return render(request, "error.html",
                                              {"error": "You uploaded an unsupported quarantine file."})

                for gw in task_gateways:
                    options = update_options(gw, orig_options)

                    for entry in task_machines:
                        task_ids_new = db.demux_sample_and_add_to_db(file_path=path, package=package, timeout=timeout, options=options, priority=priority,
                                                                     machine=entry, custom=custom, memory=memory, enforce_timeout=enforce_timeout, tags=tags, clock=clock)
                        task_ids.extend(task_ids_new)
        elif "pcap" in request.FILES:
            samples = request.FILES.getlist("pcap")
            for sample in samples:
                if not sample.size:
                    if len(samples) != 1:
                        continue
                    
                    return render(request, "error.html",
                                              {"error": "You uploaded an empty PCAP file."})
                elif sample.size > settings.MAX_UPLOAD_SIZE:
                    return render(request, "error.html",
                                              {"error": "You uploaded a PCAP file that exceeds the maximum allowed upload size specified in web/web/local_settings.py."})

                # Moving sample from django temporary file to Cuckoo temporary storage to
                # let it persist between reboot (if user like to configure it in that way).
                path = store_temp_file(sample.read(),
                                       sample.name)

                if sample.name.lower().endswith(".saz"):
                    saz = saz_to_pcap(path)
                    if saz:
                        try:
                            os.remove(path)
                        except:
                            pass
                        path = saz
                    else:
                        return render(request, "error.html",
                                                  {"error": "Conversion from SAZ to PCAP failed."})
       
                task_id = db.add_pcap(file_path=path, priority=priority)
                task_ids.append(task_id)

        elif "url" in request.POST and request.POST.get("url").strip():
            url = request.POST.get("url").strip()
            if not url:
                return render(request, "error.html",
                                          {"error": "You specified an invalid URL!"})

            url = url.replace("hxxps://", "https://").replace("hxxp://", "http://").replace("[.]", ".")
            for gw in task_gateways:
                options = update_options(gw, orig_options)

                for entry in task_machines:
                    task_id = db.add_url(url=url,
                                         package=package,
                                         timeout=timeout,
                                         options=options,
                                         priority=priority,
                                         machine=entry,
                                         custom=custom,
                                         memory=memory,
                                         enforce_timeout=enforce_timeout,
                                         tags=tags,
                                         clock=clock)
                    if task_id:
                        task_ids.append(task_id)
        elif settings.VTDL_ENABLED and "vtdl" in request.POST:
            vtdl = request.POST.get("vtdl").strip()
            if (not settings.VTDL_PRIV_KEY and not settings.VTDL_INTEL_KEY) or not settings.VTDL_PATH:
                    return render(request, "error.html",
                                              {"error": "You specified VirusTotal but must edit the file and specify your VTDL_PRIV_KEY or VTDL_INTEL_KEY variable and VTDL_PATH base directory"})
            else:
                base_dir = tempfile.mkdtemp(prefix='cuckoovtdl',dir=settings.VTDL_PATH)
                hashlist = []
                if "," in vtdl:
                    hashlist=vtdl.split(",")
                else:
                    hashlist.append(vtdl)
                onesuccess = False

                for h in hashlist:
                    filename = base_dir + "/" + h
                    if settings.VTDL_PRIV_KEY:
                        url = 'https://www.virustotal.com/vtapi/v2/file/download'
                        params = {'apikey': settings.VTDL_PRIV_KEY, 'hash': h}
                    else:
                        url = 'https://www.virustotal.com/intelligence/download/'
                        params = {'apikey': settings.VTDL_INTEL_KEY, 'hash': h}

                    try:
                        r = requests.get(url, params=params, verify=True)
                    except requests.exceptions.RequestException as e:
                        return render(request, "error.html",
                                              {"error": "Error completing connection to VirusTotal: {0}".format(e)})
                    if r.status_code == 200:
                        try:
                            f = open(filename, 'wb')
                            f.write(r.content)
                            f.close()
                        except:
                            return render(request, "error.html",
                                              {"error": "Error writing VirusTotal download file to temporary path"})

                        onesuccess = True

                        for gw in task_gateways:
                            options = update_options(gw, orig_options)

                            for entry in task_machines:
                                task_ids_new = db.demux_sample_and_add_to_db(file_path=filename, package=package, timeout=timeout, options=options, priority=priority,
                                                                             machine=entry, custom=custom, memory=memory, enforce_timeout=enforce_timeout, tags=tags, clock=clock)
                                task_ids.extend(task_ids_new)
                    elif r.status_code == 403:
                        return render(request, "error.html",
                                                  {"error": "API key provided is not a valid VirusTotal key or is not authorized for VirusTotal downloads"})


                if not onesuccess:
                    return render(request, "error.html",
                                              {"error": "Provided hash not found on VirusTotal"})



        tasks_count = len(task_ids)
        if tasks_count > 0:
            return render(request, "submission/complete.html",
                                      {"tasks" : task_ids,
                                       "tasks_count" : tasks_count})
        else:
            return render(request, "error.html",
                                      {"error": "Error adding task to Cuckoo's database."})
    else:
        enabledconf = dict()
        enabledconf["vt"] = settings.VTDL_ENABLED
        enabledconf["kernel"] = settings.OPT_ZER0M0N
        enabledconf["memory"] = Config("processing").memory.get("enabled")
        enabledconf["procmemory"] = Config("processing").procmemory.get("enabled")
        enabledconf["tor"] = Config("auxiliary").tor.get("enabled")
        if Config("auxiliary").gateways:
            enabledconf["gateways"] = True
        else:
            enabledconf["gateways"] = False
        enabledconf["tags"] = False
        # Get enabled machinery
        machinery = Config("cuckoo").cuckoo.get("machinery")
        # Get VM names for machinery config elements
        vms = [x.strip() for x in getattr(Config(machinery), machinery).get("machines").split(",")]
        # Check each VM config element for tags
        for vmtag in vms:
            if "tags" in getattr(Config(machinery), vmtag).keys():
                enabledconf["tags"] = True

        files = os.listdir(os.path.join(settings.CUCKOO_PATH, "analyzer", "windows", "modules", "packages"))

        packages = []
        for name in files:
            name = os.path.splitext(name)[0]
            if name == "__init__":
                continue

            packages.append(name)

        # Prepare a list of VM names, description label based on tags.
        machines = []
        for machine in Database().list_machines():
            tags = []
            for tag in machine.tags:
                tags.append(tag.name)

            if tags:
                label = machine.label + ": " + ", ".join(tags)
            else:
                label = machine.label

            machines.append((machine.label, label))

        # Prepend ALL/ANY options.
        machines.insert(0, ("", "First available"))
        machines.insert(1, ("all", "All"))

        return render(request, "submission/index.html",
                                  {"packages": sorted(packages),
                                   "machines": machines,
                                   "gateways": settings.GATEWAYS,
                                   "config": enabledconf})

@conditional_login_required(login_required, settings.WEB_AUTHENTICATION)
def status(request, task_id):
    task = Database().view_task(task_id)
    if not task:
        return render(request, "error.html",
                                  {"error": "The specified task doesn't seem to exist."})

    completed = False
    if task.status == "reported":
        return redirect('report', task_id=task_id)

    status = task.status
    if status == "completed":
        status = "processing"

    return render(request, "submission/status.html",
                              {"completed" : completed,
                               "status" : status,
                               "task_id" : task_id})
