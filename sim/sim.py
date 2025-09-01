from tools import *
from sim.hw_system import *
from sim.inst_queue import *
import tqdm
import pickle as pkl
from math import inf
import numpy as np

tqdm_copy = tqdm.tqdm # store it if you want to use it later

def tqdm_replacement(iterable_object,*args,**kwargs):
    return iterable_object

def sim(commands, silent=False, filename=None, sim_verify = False, use_tqdm = True):
    
    # set up sim config
    # SimConfig.read_from_yaml('./config/all_feature.yaml')
    
    # NOTE: if you want to disable tqdm in the framework, you can use the following code

    if not silent: assert use_tqdm
    if not use_tqdm:
        tqdm.tqdm = tqdm_replacement
    else:
        tqdm.tqdm = tqdm_copy

    # create HW
    real_ch = SimConfig.ch
    # NOTE: speedup the simulation, but turn off when comparing to Samsung's Simulator
    if not sim_verify:
        SimConfig.ch = 1

    np_bankstate = np.zeros((SimConfig.ch, SimConfig.ra, SimConfig.de, SimConfig.bg*SimConfig.ba, 4), dtype=np.int64)
    de_state_num = 1 + 1 + max(SimConfig.de_pu) # bus, buffer, pu
    ra_state_num = SimConfig.de + 1 + SimConfig.ra_pu # bus, buffer, pu
    ch_state_num = 0 # bus, buffer, pu
    sys_state_num = SimConfig.ch
    resource_state = np.zeros(sys_state_num + SimConfig.ch * (ch_state_num + SimConfig.ra * (ra_state_num + (SimConfig.de * de_state_num))), dtype=np.int64)
    HW = HW_system(np_bankstate, resource_state)

    # create inst queue
    queue = inst_queue()

    total_cmd = 0

    if filename is not None:
        commands = []
        with open(filename, 'rb') as f:
            commands = pkl.load(f)

    for cmd in commands:
        queue.add_group(cmd[0], cmd[1], cmd[2])
        total_cmd += len(cmd[2])
    
    global_tick = 0
    issue_cmd = None
    issue_group = None
    # use tqdm to show progress
    for _ in tqdm.tqdm(range(total_cmd+1), leave=False, desc="Simulation"):
    # for _ in range(total_cmd+1):
    # while not queue.check_empty():
        if issue_cmd is not None: # skip the first cycle
        # 1. update states
            # 检查bankstate是否溢出
            if np.any(np_bankstate < 0):
                raise ValueError("bankstate出现负值溢出，请增加延迟表示范围")

            # if add_tick > 0:
            #     global_tick += add_tick
            #     # HW.update(add_tick)
            #     np_bankstate += -int(add_tick)
            #     np_bankstate.clip(0)
            #     resource_state += -int(add_tick)
            #     resource_state.clip(0)
        # 2. issue command (覆盖指令涉及部分的 states)
            # queue
            queue.issue_inst(issue_group)
            queue.clear_empty_group(issue_group)
            # hardware
            if not silent: 
                tqdm.tqdm.write(f"tick: {add_tick}, group: {issue_group}, cmd: {issue_cmd}")
            HW.issue_inst(issue_cmd, issue_group)
            # log
            issue_cmd = None
            issue_group = None
        add_tick = inf
        # 3. find next command to issue
        issuable_cmd = queue.get_inst()
        # choose 1 cmd to issue, TODO: try different strategies
        
        for tmp in issuable_cmd:
            group_id, inst_tmp = tmp
            tmp_issue_lat = HW.check_inst(inst_tmp, group_id)
            # report
            # print(f"group: {group_id}, inst: {inst_tmp}, issue_lat: {tmp_issue_lat}")
            if tmp_issue_lat < add_tick:
                add_tick = tmp_issue_lat
                issue_cmd = inst_tmp
                issue_group = group_id
    
    # TODO: how to get final latency?
    #   把资源状态里的最大值加到全局时钟上
    global_tick += np.max(resource_state)

    SimConfig.ch = real_ch
    return global_tick