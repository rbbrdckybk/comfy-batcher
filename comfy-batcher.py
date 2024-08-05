# Copyright 2024, Bill Kennedy (https://github.com/rbbrdckybk)
# SPDX-License-Identifier: MIT

# Usage help: python comfy-batcher.py --help
# Example: python comfy-batcher.py --workflow_file flux_workflow_api.json --prompt_file example-prompts.txt

import json
import re
from urllib import request, parse
from os.path import exists
from collections import deque
from datetime import datetime as dt
import random
import argparse

# for easy reading of prompt files
class TextFile():
    def __init__(self, filename):
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

    def next_line(self):
        return self.lines.popleft()

    def lines_remaining(self):
        return len(self.lines)

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

# entry point
if __name__ == '__main__':
    print('\nStarting...')

    # get command-line args
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
        '--workflow_file',
        type=str,
        required=True,
        help='JSON file containing a ComfyUI workflow'
    )
    ap.add_argument(
        '--output_file_prefix',
        type=str,
        default='flux_<date>',
        help='prefix to prepend to your output files'
    )
    ap.add_argument(
        '--width',
        type=int,
        default=1024,
        help='width of output image in pixels'
    )
    ap.add_argument(
        '--height',
        type=int,
        default=1024,
        help='height of output image in pixels'
    )
    ap.add_argument(
        '--guidance',
        type=float,
        default=3.5,
        help='cfg guidance scale'
    )
    ap.add_argument(
        '--sampler',
        type=str,
        default='euler',
        help='sampler to use'
    )
    ap.add_argument(
        '--scheduler',
        type=str,
        default='simple',
        help='scheduler to use'
    )
    ap.add_argument(
        '--steps',
        type=int,
        default=20,
        help='number of steps'
    )
    options = ap.parse_args()
    if options.server_addr.endswith('/'):
        options.server_addr = options.server_addr[:-1]

    # ensure required files exist
    if not exists(options.prompt_file):
        print('Error: specified prompt file ' + options.prompt_file + ' does not exist; aborting!')
        exit(-1)
    if not exists(options.workflow_file):
        print('Error: specified workflow file ' + options.workflow_file + ' does not exist; aborting!')
        exit(-1)

    # load the workflow from fil, assign it to variable named prompt_workflow
    workflow = None
    try:
        workflow = json.load(open(options.workflow_file))
    except Exception as e:
        print('Failed to load workflow file:', repr(e))
        print('Aborting!')
        exit(-1)

    # locate necessary workflow nodes
    prompt_node = None
    noise_node = None
    size_node = None
    guidance_node = None
    sampler_node = None
    scheduler_node = None
    save_node = None
    print('\nSearching for nodes in workflow...')
    for node in workflow:
        data = workflow[node]
        if "_meta" in data and "title" in data["_meta"]:
            #print(data["_meta"]["title"])
            if data["_meta"]["title"].lower().strip() == 'clip text encode (prompt)':
                print('  Found prompt node...')
                prompt_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'randomnoise':
                print('  Found noise node...')
                noise_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'empty latent image':
                print('  Found size node...')
                size_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'fluxguidance':
                print('  Found guidance node...')
                guidance_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'ksamplerselect':
                print('  Found sampler node...')
                sampler_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'basicscheduler':
                print('  Found scheduler node...')
                scheduler_node = workflow[node]
            elif data["_meta"]["title"].lower().strip() == 'save image':
                print('  Found output filename node...')
                save_node = workflow[node]

    if prompt_node == None:
        print('Unable to locate prompt node in workflow; aborting!')
        exit(-1)

    # Read prompts from specified prompt file and send to ComfyUI via API
    count = 0
    pf = TextFile(options.prompt_file)
    print('\nFound ' + str(pf.lines_remaining()) + ' prompts in ' + options.prompt_file + '...')

    if pf.lines_remaining() > 0:
        print('\nSending prompts to ' + str(options.server_addr) + '...')
        while pf.lines_remaining() > 0:
            count += 1
            # set the text prompt for positive CLIPTextEncode node
            prompt = pf.next_line()
            prompt_node["inputs"]["text"] = prompt
            rseed = random.randint(1, 18446744073709551614)
            if noise_node != None:
                noise_node["inputs"]["noise_seed"] = rseed
            if sampler_node != None:
                sampler_node["inputs"]["sampler_name"] = options.sampler
            if scheduler_node != None:
                scheduler_node["inputs"]["scheduler"] = options.scheduler
                scheduler_node["inputs"]["steps"] = options.steps
            if guidance_node != None:
                guidance_node["inputs"]["guidance"] = options.guidance
            if size_node != None:
                size_node["inputs"]["width"] = options.width
                size_node["inputs"]["height"] = options.height
            if save_node != None:
                prefix = options.output_file_prefix
                prefix = re.sub('<width>', str(options.width), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<height>', str(options.height), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<sampler>', str(options.sampler), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<scheduler>', str(options.scheduler), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<steps>', str(options.steps), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<guidance>', str(options.guidance), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<seed>', str(rseed), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<date>', dt.now().strftime('%Y%m%d'), prefix, flags=re.IGNORECASE)
                prefix = re.sub('<time>', dt.now().strftime('%H%M%S'), prefix, flags=re.IGNORECASE)
                save_node["inputs"]["filename_prefix"] = prefix

            status = queue_prompt(workflow, options.server_addr, options.auth_token)
            if status == '':
                print('\n  Queued prompt #' + str(count) + ': ' + prompt)
            else:
                print('\n  Error sending prompt #' + str(count) + ': ' + status)

    print('\nDone!')
