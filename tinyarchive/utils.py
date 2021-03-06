# TinyArchive - A tiny web archive
# Copyright (C) 2012-2013 David Triendl
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import hashlib
import itertools
import json
import logging
import os
import os.path
import shutil
import subprocess

def _code_order(char):
    if char >= '0' and char <= '9':
        return 0
    elif char >= 'a' and char <= 'z':
        return 1
    elif char >= 'A' and char <= 'Z':
        return 2
    return 3

def shortcode_compare(a, b):
    diff = len(a) - len(b)
    if diff:
        return diff
    for a, b in itertools.izip(a, b):
        if a != b:
            diff = _code_order(a) - _code_order(b)
            if diff:
                return diff
            else:
                return ord(a) - ord(b)
    return 0

class CodeToFileMap:

    def __init__(self, input_file):
        with open(input_file) as fileobj:
            unsorted_map = json.load(fileobj)

        self._map = {}
        for (service, service_map) in unsorted_map.iteritems():
            if len(service_map) == 1:
                self._map[service] = service_map
            else:
                self._map[service] = sorted(service_map, cmp=self._compare_mapping)

        self.check()

    def check(self):
        output_files = set()
        for (service, service_map) in self._map.iteritems():
            for (i, mapping) in enumerate(service_map):
                if not "file" in mapping:
                    raise ValueError("No file specified for service '%s', mapping %i" % (service, i+1))
                if mapping["file"] in output_files:
                    raise ValueError("Duplicate output file '%s'" % mapping["file"])
                output_files.add(mapping["file"])
            if len(service_map) == 1:
                if len(service_map[0]) != 1:
                    raise ValueError("Additional data for service '%s', mapping 1" % service)
            else:
                previous = ""
                for i, mapping in enumerate(service_map):
                    if not "start" in mapping or not "stop" in mapping:
                        raise ValueError("Start or stop not given for service '%s', mapping %i" % (service, i+1))
                    if len(mapping) != 3:
                        raise ValueError("Additional data for service '%s', mapping %i" % (service, i+1))
                    if shortcode_compare(mapping["start"], mapping["stop"]) > 0:
                        raise ValueError("Start is bigger than stop for service '%s', mapping %i" % (service, i+1))
                    if shortcode_compare(previous, mapping["start"]) >= 0:
                        print previous
                        print mapping
                        raise ValueError("Overlap detected for service '%s', code '%s'" % (service, previous))
                    previous = mapping["stop"]

    def get_mapping(self, service, start):
        service_map = self._map[service]
        if len(service_map) == 1:
            return service_map[0]
        else:
            for mapping in service_map:
                if shortcode_compare(start, mapping["start"]) >= 0 and shortcode_compare(start, mapping["stop"]) <= 0:
                    return mapping
        raise ValueError("No mapping for service '%s', code '%s' found" % (service, start))


    def check_mapping(self, mapping, stop):
        if not "stop" in mapping:
            return True
        return shortcode_compare(stop, mapping["stop"]) <= 0

    def _compare_mapping(self, x, y):
        return shortcode_compare(x["start"], y["start"])

    def get_service(self, filename):
        for (service, service_map) in self._map.iteritems():
            for mapping in service_map:
                if filename == mapping["file"]:
                    return service
        raise ValueError("File '%s' not found in mapping table" % filename)

class OutputFile:

    def __init__(self, old_release_directory, new_release_directory, output_file):
        self._log = logging.getLogger("tinyarchive.utils.OutputFile")
        self._log.info("Opening output file %s" % output_file)

        self._old_file = os.path.join(old_release_directory, output_file)
        self._new_file = os.path.join(new_release_directory, output_file)
        if not os.path.isdir(os.path.dirname(self._new_file)):
            os.makedirs(os.path.dirname(self._new_file))

        self._fileobj = open(self._new_file + ".txt", "wb")

        self._hash = None
        if os.path.isfile(self._old_file + ".txt.xz"):
            self._hash = hashlib.md5()
            self._subproc = subprocess.Popen("xzcat '%s.txt.xz' | md5sum" % self._old_file, shell=True, stdout=subprocess.PIPE)

    def write(self, code, url):
        if self._hash:
            self._hash.update(code + "|")
            self._hash.update(url)
            self._hash.update("\n")
        self._fileobj.write(code + "|")
        self._fileobj.write(url)
        self._fileobj.write("\n")

    def close(self):
        self._log.debug("Closing output file")
        self._fileobj.close()

        if self._hash:
            self._log.debug("Calculating output file hash")
            new_hash = self._hash.hexdigest()

            self._subproc.wait()
            old_hash = self._subproc.communicate()[0][:32]
            self._log.debug("Hash of old previous release file: %s" % old_hash)

            if old_hash == new_hash:
                self._log.info("File did not change since last release")
                os.unlink(self._new_file + ".txt")
                shutil.copyfile(self._old_file + ".txt.xz", self._new_file + ".txt.xz")
                return

        subprocess.check_call(["xz", "-9", self._new_file + ".txt"])
