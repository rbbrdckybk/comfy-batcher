# Copyright 2024, Bill Kennedy (https://github.com/rbbrdckybk)
# SPDX-License-Identifier: MIT

# Usage help: python comfy-batcher.py --help
# Example: python comfy-batcher.py --workflow_file flux_workflow_api.json --prompt_file example-prompts.txt

import json
import re
import unicodedata
from urllib import request, parse
from tqdm import tqdm
from os.path import exists
from collections import deque
from datetime import datetime as dt
import random
import argparse
import copy

# for organizing workflow nodes
class Node:
  def __init__(self):
    self.arg_name = ''
    self.arg_value = ''
    self.mapping_node_path = ''
    self.actual_node = None

# for 1-to-many mappings
class Dictlist(dict):
    def __setitem__(self, key, value):
        if key not in self:
            super(Dictlist, self).__setitem__(key, [])
        self[key].append(value)

# for easy reading of prompt files
class TextFile():
    def __init__(self, filename):
        self.total_non_directives = 0
        self.lines = deque()
        if exists(filename):
            with open(filename, encoding = 'utf-8') as f:
                l = f.readlines()

            for x in l:
                # remove newline and whitespace
                x = x.strip('\n').strip();
                # remove comments
                x = x.split('#', 1)[0].strip();
                if x != "":
                    # these lines are actual prompts
                    self.lines.append(x)
                    if x[0] != '!':
                        self.total_non_directives += 1

    def next_line(self):
        return self.lines.popleft()

    def lines_remaining(self):
        return len(self.lines)

    def total_non_directives(self):
        return self.total_non_directives

def queue_prompt(prompt_workflow, address = 'http://127.0.0.1', token = ''):
    status = ''
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    headers = {}
    if token != '':
        headers = {
            'Authorization': f'Bearer {token}',
        }
    req =  request.Request(address + '/prompt', data=data, headers=headers)
    try:
        request.urlopen(req)
    except Exception as e:
        #print('API request failed:', repr(e))
        status = repr(e)
    else:
        status = ''
    return status


# Taken from https://github.com/django/django/blob/master/django/utils/text.py
# Using here to make filesystem-safe names
def slugify(value, allow_unicode=False, allow_pathsep=False):
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    if allow_pathsep:
        # added 2025-04-12 BK, allows path separators if specified
        value = re.sub(r'[^\w\s-][\\\/]', '', value.lower())
    else:
        value = re.sub(r'[^\w\s-]', '', value.lower())
    value = re.sub(r'[-\s]+', '-', value).strip('-_')
    return value


# sets nested value in dict d to value using keys
# e.g. d[key[0]][key[1]]... = value
def set_nested_value(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


# entry point
if __name__ == '__main__':
    print('\nStarting...\n')

    # define command-line args
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--server_addr',
        type=str,
        default='http://127.0.0.1',
        help='ComfyUI server address to connect to (default = http://127.0.0.1)'
    )
    ap.add_argument(
        '--auth_token',
        type=str,
        default='',
        help='authentication token (if using ComfyUI-Login)'
    )
    ap.add_argument(
        '--prompt_file',
        type=str,
        required=True,
        help='text file containing a list of prompts to queue'
    )
    ap.add_argument(
        '--prompt_prepend',
        type=str,
        default='',
        help='text to prepend to every prompt (optional)'
    )
    ap.add_argument(
        '--prompt_append',
        type=str,
        default='',
        help='text to append to every prompt (optional)'
    )
    ap.add_argument(
        '--workflow_file',
        type=str,
        required=True,
        help='JSON file containing a ComfyUI workflow'
    )
    ap.add_argument(
        '--truncate_prompt_length',
        type=int,
        default=0,
        help='set an optional character limit to truncate prompts at; 0 = no limit'
    )

    # grab arbitrary user args as strings
    parsed, unknown = ap.parse_known_args()
    for arg in unknown:
        if arg.startswith(("-", "--")):
            arg_name = arg.split('=')[0]
            if arg_name.lower() != 'prompt':
                ap.add_argument(
                    arg_name,
                    type=str
                )
    options = ap.parse_args()

    # store user-defined arg names for later
    user_defined_args = []
    for option in vars(options):
        if option not in parsed:
            user_defined_args.append(option.lower())

    if options.server_addr.endswith('/'):
        options.server_addr = options.server_addr[:-1]

    # ensure required files exist
    map_filename = options.workflow_file + '.map'
    if not exists(options.prompt_file):
        print('Error: specified prompt file "' + options.prompt_file + '" does not exist; aborting!')
        exit(-1)
    if not exists(options.workflow_file):
        print('Error: specified workflow file "' + options.workflow_file + '" does not exist; aborting!')
        exit(-1)
    if not exists(map_filename):
        print('Error: specified workflow file "' + options.workflow_file + '" has no associated mapping file ("' + map_filename + '"); aborting!')
        exit(-1)

    # load the workflow file as JSON
    workflow = None
    try:
        workflow = json.load(open(options.workflow_file, encoding='utf-8'))
    except Exception as e:
        print('Failed to load workflow file:', repr(e))
        print('Aborting!')
        exit(-1)
    else:
        print('Loaded workflow file "' + options.workflow_file + '" successfully.')

    # load the associated workflow map file
    nodes = []
    count = 0
    found_prompt_mapping = False
    #mappings = {}
    mappings = Dictlist()
    mf = TextFile(map_filename)
    while mf.lines_remaining() > 0:
        line = mf.next_line()
        if '==' in line:
            count += 1
            var = line.split('==', 1)[0].lower().strip()
            node_loc = line.split('==', 1)[1].strip()
            if ',' in node_loc:
                # handle 1-to-many mappings
                node_locs = node_loc.split(',')
                for nl in node_locs:
                    mappings[var] = nl.strip()
            else:
                mappings[var] = node_loc
            if var.lower() == 'prompt':
                found_prompt_mapping = True
                if ',' in node_loc:
                    for nl in node_locs:
                        node = Node()
                        node.arg_name = 'prompt'
                        node.mapping_node_path = nl.strip()
                        nodes.append(node)
                else:
                    node = Node()
                    node.arg_name = 'prompt'
                    node.mapping_node_path = node_loc
                    nodes.append(node)

    if found_prompt_mapping:
        print('Loaded mapping file "' + map_filename + '" successfully (found ' + str(count) + ' defined mappings).')
    else:
        print('Error: specified mapping file "' + map_filename + '" does not contain required "prompt" mapping!')
        print('Aborting!')
        exit(-1)

    # locate necessary workflow nodes that we have user-supplied arguments for
    for arg in user_defined_args:
        if arg in mappings:
            for path in mappings[arg]:
                node = Node()
                node.arg_name = arg
                node.arg_value = getattr(options, arg)
                node.mapping_node_path = path
                nodes.append(node)
        else:
            print(' - Warning: no mapping found for passed argument: --' + arg)

    print('Searching for nodes in workflow...')
    for node_mapping in nodes:
        title = node_mapping.mapping_node_path
        keys = []
        if '/' in node_mapping.mapping_node_path:
            title = node_mapping.mapping_node_path.split('/', 1)[0]
            keys = node_mapping.mapping_node_path.split('/', 1)[1]
            keys = keys.split('/')
        # attempt to find this mapping on the actual JSON
        for node in workflow:
            data = workflow[node]
            if data["_meta"]["title"].strip() == title:
                node_mapping.actual_node = workflow[node]
                temp = node_mapping.actual_node
                for key in keys:
                    if key in temp:
                        temp = temp[key]
                    else:
                        # one of the keys does not exist; invalidate this
                        node_mapping.actual_node = None
                        break
                break

    # let user know about any unvalidated nodes
    count = 0
    found_nodes = ''
    for node_mapping in nodes:
        if node_mapping.actual_node == None:
            if node_mapping.arg_name != 'prompt':
                print(' - Warning: specified mapping node (for arg --' + str(node_mapping.arg_name) + ') does not exist in JSON workflow: "' + str(node_mapping.mapping_node_path) + '"')
            else:
                print('Error: Unable to locate specified required prompt node ("' + node_mapping.mapping_node_path + '") in workflow; aborting!')
                exit(-1)
        else:
            if count > 0:
                found_nodes += ', '
            found_nodes += node_mapping.arg_name
            count += 1
    print(' - Successfully located ' + str(count) + ' defined mapping nodes (' + found_nodes + ') in JSON workflow that arguments were supplied for.')

    # Read prompts from specified prompt file and send to ComfyUI via API
    count = 0
    pf = TextFile(options.prompt_file)
    print('Found ' + str(pf.lines_remaining()) + ' prompts in ' + options.prompt_file + '.')

    if pf.lines_remaining() > 0:
        print('\nSending prompts to ' + str(options.server_addr) + '...')
        pbar = tqdm(total = pf.total_non_directives)
        directives = {}
        while pf.lines_remaining() > 0:
            prompt = pf.next_line()
            if prompt.strip()[0] == '!' and '=' in prompt:
                # this is a directive
                before = prompt.split('=', 1)[0].strip()[1:]
                after = prompt.split('=', 1)[1].strip()
                # check to make sure we have a valid mapping and default value for this override
                if before.lower() in mappings:
                    found = False
                    for node_mapping in nodes:
                        if node_mapping.arg_name.lower() == before.lower():
                            found = True
                            break
                    if found:
                        directives.update({before.lower() : after})
                        #print('\nAdded mapping for specified directive override: !' + before.upper())
                    else:
                        print('\nWarning: specified directive: !' + before.upper() + ' has no default mapping value; pass in initial arguments before using override!')
                else:
                    print('\nWarning: no mapping for specified directive: !' + before.upper())
            else:
                # this is a prompt
                count += 1
                if options.prompt_prepend != '':
                    prompt = options.prompt_prepend + ' ' + prompt
                if options.prompt_append != '':
                    prompt += ' ' + options.prompt_append
                if options.truncate_prompt_length > 0:
                    prompt = prompt[:options.truncate_prompt_length]
                rand = random.randint(1, 999999999999999)
                for node_mapping in nodes:
                    # make updates to the JSON for all good mappings we have
                    if node_mapping.actual_node != None:
                        # check for directive value override
                        if node_mapping.arg_name.lower() in directives:
                            #print('Found ' + node_mapping.arg_name.lower() + ' in directives!')
                            value = directives.get(node_mapping.arg_name.lower())
                            #print('Using ' + value + ' instead of ' + node_mapping.arg_value)
                        else:
                            value = node_mapping.arg_value
                        path = node_mapping.mapping_node_path
                        # handle special args
                        if node_mapping.arg_name.lower() == 'prompt':
                            value = prompt
                        elif node_mapping.arg_name.lower() == 'seed':
                            if value.lower().strip() in ['random', '0', '-1', '?']:
                                value = str(rand)
                        elif (
                            'file' in node_mapping.arg_name.lower()
                            and
                            ('name' in node_mapping.arg_name.lower()
                            or
                            'path' in node_mapping.arg_name.lower())
                        ):
                            # make requested substitutions in filename arg
                            if 'path' in node_mapping.arg_name.lower():
                                value = re.sub('<prompt>', slugify(prompt[:100], False, True), value, flags=re.IGNORECASE)
                            else:
                                value = re.sub('<prompt>', slugify(prompt[:100]), value, flags=re.IGNORECASE)
                            value = re.sub('<date>', dt.now().strftime('%Y%m%d'), value, flags=re.IGNORECASE)
                            value = re.sub('<time>', dt.now().strftime('%H%M%S'), value, flags=re.IGNORECASE)
                            # do user-variable subs if necessary
                            while '<' in value and '>' in value:
                                before = value.split('<', 1)[0]
                                remaining = value.split('<', 1)[1]
                                if '>' not in remaining:
                                    break
                                keyword = remaining.split('>', 1)[0]
                                after = remaining.split('>', 1)[1]
                                found = False
                                for n in nodes:
                                    if keyword.lower().strip() == n.arg_name.lower().strip():
                                        found = True
                                        if keyword == 'seed' and n.arg_value in ['random', '0', '-1', '?']:
                                            keyword = str(rand)
                                        elif str(n.arg_value).lower().endswith('.safetensors'):
                                            keyword = str(n.arg_value)[:-12]
                                        elif str(n.arg_value).lower().endswith('.sft'):
                                            keyword = str(n.arg_value)[:-4]
                                        else:
                                            keyword = str(n.arg_value)
                                        break
                                if found:
                                    value = before + keyword + after
                                else:
                                    value = before + after

                            # limit total prefix length to 200 chars & make it filesystem-safe
                            value = value[:200]
                            if 'path' in node_mapping.arg_name.lower():
                                value = slugify(value, False, True)
                            else:
                                value = slugify(value)


                        keys = node_mapping.mapping_node_path.split('/', 1)[1]
                        keys = keys.split('/')
                        # update the JSON with the user-supplied value
                        set_nested_value(node_mapping.actual_node, keys, value)

                status = queue_prompt(workflow, options.server_addr, options.auth_token)
                pbar.update(1)
                if status != '':
                    print('\n  Error sending prompt #' + str(count) + ': ' + status)

        pbar.close()
    print('\nDone!')
