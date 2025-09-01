"""

rank:

bank pu
bank (sub-class)
device bus
device buffer

"""
from tools import *
from sim.device import *
from math import inf
# from joblib import Parallel, delayed

class Rank:

    def __init__(self, channel_id, rank_id, bankstate, resource_state):
        self.id = (channel_id, rank_id)
        self.devices = []
        self.device_buses = []
        self.physical_pu_num = SimConfig.ra_pu
        rank_resource_state = resource_state[:SimConfig.de+1+self.physical_pu_num]
        self.buffer = Buffer(SimConfig.ra_gb, rank_resource_state, SimConfig.de)
        self.last_cmd_info = {}
        # self.mvm_unit = None # 输入宽度由dram能给多少数决定，输出宽度由mvm_unit能存多少数决定，但是得把权重都存下来？
        self.pu = []
        rank_state_len = (resource_state.shape[0] - SimConfig.de - 1 - self.physical_pu_num) // SimConfig.de

        # init banks
        for i in range(SimConfig.de):
            self.devices.append(Device(channel_id, rank_id, i, bankstate, \
                                       resource_state[SimConfig.de+1+self.physical_pu_num+i*rank_state_len:\
                                                      SimConfig.de+1+self.physical_pu_num+(i+1)*rank_state_len]))

        # init device buses 
        for i in range(SimConfig.de):
            self.device_buses.append(Resource(rank_resource_state, i))

        # init rank pus
        self.physical_pu_num = SimConfig.ra_pu
        for i in range(self.physical_pu_num):
            self.pu.append(PU(rank_resource_state, SimConfig.de + 1 + i))

    def check_inst(self, inst, inst_group):
        if inst[0] == LEVEL.RA:
            if inst[1] == OPTYPE.pu:
                # decode
                pu_num, pu_mask = inst[4]
                op1_device, op1_bank, op1_row_id, op1_col_offset = inst[5]
                op2_device, op2_bank, op2_row_id, op2_col_offset = inst[6]
                col_num = inst[7]
                pu_connected_device = SimConfig.de / pu_num
                auto_precharge = inst[8]
                ultilized_pu = [i for i in range(pu_num) if pu_mask[i]]
                actual_pu_list = [int(i * self.physical_pu_num / pu_num) for i in ultilized_pu]
                op1_src_device = [int(i * pu_connected_device + op1_device) for i in ultilized_pu]
                if op1_device == op2_device:
                    # 在op2的row空间划分本地的输入buffer和device的输入buffer，目前先按照row=0为本地的input buffer
                    if op2_row_id > 0: # compute using gb
                        assert SimConfig.ra_gb > 0
                        pass
                        
                    else:
                        # NOTE: Bank-level NMP(UPMEM-like), pu read from self input buffer & related bank
                        assert SimConfig.ra_pu_inbuf > 0
                        # sync point
                        sync_point = 0
                        for i, pu_id in enumerate(actual_pu_list):
                            src1_sync_point = sum(self.devices[op1_src_device[i]]\
                                                .banks[op1_bank].check_inst(op1_row_id, write=False)) + SimConfig.RL
                            # src2_sync_point = sum(self.devices[op2_src_device[i]]\
                            #                     .banks[op2_bank].check_inst(op2_row_id, write=False)) + SimConfig.RL
                            pu_sync_point = self.pu[pu_id].check_state() - SimConfig.BL/2
                            device_inner_bus_sync_point = self.devices[op1_src_device[i]].bus.check_state()
                            sync_point = max(sync_point, src1_sync_point, pu_sync_point, device_inner_bus_sync_point)
                        # issue point
                        issue_time = inf
                        for i, pu_id in enumerate(actual_pu_list):
                            src1_issue_time = sync_point - self.devices[op1_src_device[i]]\
                                                .banks[op1_bank].check_inst(op1_row_id, write=False)[1] - SimConfig.RL
                            # src2_issue_time = sync_point - self.devices[op2_src_device[i]]\
                            #                     .banks[op2_bank].check_inst(op2_row_id, write=False)[1] - SimConfig.RL
                            # issue_time = min(issue_time, src1_issue_time, src2_issue_time)
                            issue_time = min(issue_time, src1_issue_time)
                        self.last_cmd_info[inst_group] = sync_point
                        return issue_time
                else:
                    op2_src_device = [int(i * pu_connected_device + op2_device) for i in ultilized_pu]
                    # sync point
                    sync_point = 0
                    for i, pu_id in enumerate(actual_pu_list):
                        src1_sync_point = sum(self.devices[op1_src_device[i]]\
                                            .banks[op1_bank].check_inst(op1_row_id, write=False)) + SimConfig.RL
                        src2_sync_point = sum(self.devices[op2_src_device[i]]\
                                            .banks[op2_bank].check_inst(op2_row_id, write=False)) + SimConfig.RL
                        pu_sync_point = self.pu[pu_id].check_state() - SimConfig.BL/2
                        device_inner_bus_sync_point = max(self.devices[op1_src_device[i]].bus.check_state(),
                                                            self.devices[op2_src_device[i]].bus.check_state())
                        sync_point = max(sync_point, src1_sync_point, src2_sync_point, pu_sync_point, device_inner_bus_sync_point)
                    # issue point
                    issue_time = inf
                    for i, pu_id in enumerate(actual_pu_list):
                        src1_issue_time = sync_point - self.devices[op1_src_device[i]]\
                                            .banks[op1_bank].check_inst(op1_row_id, write=False)[1] - SimConfig.RL
                        src2_issue_time = sync_point - self.devices[op2_src_device[i]]\
                                            .banks[op2_bank].check_inst(op2_row_id, write=False)[1] - SimConfig.RL
                        issue_time = min(issue_time, src1_issue_time, src2_issue_time)
                    self.last_cmd_info[inst_group] = sync_point
                    return issue_time
            # op-level, op-type, ch_id, ra_id, device_mask(并口写入), (bank, row_id, col_offset), col_num, auto_precharge
            elif inst[1] == OPTYPE.bk2gb:
                # bank: bank read -> bank bus -> burst to device bus [bank, device_inter_bus]
                # device: device bus -> device buffer [device_outer_bus(TODO: bus convert), device_buffer]
                # decode
                device_mask = inst[4]
                bank_id = inst[5]
                row_id = inst[6]
                col_id = inst[7]
                gd_addr = inst[8]
                col_num = inst[9]
                auto_precharge = inst[10]
                # source list
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                sync_point = 0
                # sync point: the first data read from device
                for device_id in device_list:
                    # bank read
                    bank_sync_point = sum(self.devices[device_id].banks[bank_id]\
                        .check_inst(row_id, write=False)) + SimConfig.RL
                    # inner/outer bus
                    device_inner_bus_sync_point = self.devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.device_buses[device_id].check_state()
                    sync_point = max(sync_point, bank_sync_point, device_inner_bus_sync_point, device_outer_bus_sync_point)
                # gb write after the burst
                gb_sync_point = self.buffer.check_state() - SimConfig.BL/2
                sync_point = max(sync_point, gb_sync_point)
                # issue point
                issue_time = inf
                for device_id in device_list:
                    bank_issue_time = sync_point - self.devices[device_id].banks[bank_id]\
                        .check_inst(row_id, write=False)[1] - SimConfig.RL
                    issue_time = min(issue_time, bank_issue_time)
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] == OPTYPE.gb2bk:
                # bank: bank read -> bank bus -> burst to device bus [bank, device_inter_bus]
                # device: device bus -> device buffer [device_outer_bus(TODO: bus convert), device_buffer]
                # decode
                device_mask = inst[4]
                bank_mask = inst[5]
                row_id = inst[6]
                col_id = inst[7]
                gd_addr = inst[8]
                col_num = inst[9]
                auto_precharge = inst[10]
                # source list
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                bank_list = [i for i in range(SimConfig.ba*SimConfig.bg) if bank_mask[i]]
                sync_point = 0
                # sync point: the first data read from device
                for device_id in device_list:
                    for bank_id in bank_list:
                        # bank read
                        bank_sync_point = sum(self.devices[device_id].banks[bank_id]\
                            .check_inst(row_id, write=True)) + SimConfig.WL
                    # inner/outer bus
                    device_inner_bus_sync_point = self.devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.device_buses[device_id].check_state()
                    sync_point = max(sync_point, bank_sync_point, device_inner_bus_sync_point, device_outer_bus_sync_point)
                # gb write after the burst
                gb_sync_point = self.buffer.check_state() + SimConfig.ra_gb_rl
                sync_point = max(sync_point, gb_sync_point)
                # issue point
                issue_time = inf
                for device_id in device_list:
                    for bank_id in bank_list:
                        issue_time = min(issue_time, sync_point - self.devices[device_id].banks[bank_id]\
                            .check_inst(row_id, write=True)[1] - SimConfig.WL)
                issue_time = min(issue_time, sync_point - SimConfig.ra_gb_rl)
                self.last_cmd_info[inst_group] = sync_point
                return issue_time

        else:
            return self.devices[inst[4]].check_inst(inst, inst_group)
        
    def issue_inst(self, inst, inst_group):
        if inst[0] == LEVEL.RA:
            if inst[1] == OPTYPE.pu: 
                # decode
                pu_num, pu_mask = inst[4]
                op1_device, op1_bank, op1_row_id, op1_col_offset = inst[5]
                op2_device, op2_bank, op2_row_id, op2_col_offset = inst[6]
                col_num = inst[7]
                pu_connected_device = SimConfig.de / pu_num
                auto_precharge = inst[8]
                ultilized_pu = [i for i in range(pu_num) if pu_mask[i]]
                actual_pu_list = [int(i * self.physical_pu_num / pu_num) for i in ultilized_pu]
                op1_src_device = [int(i * pu_connected_device + op1_device) for i in ultilized_pu]
                if op1_device == op2_device:
                    # 假设不使用device间bus，而是device和pu的专属链接
                    sync_point = self.last_cmd_info[inst_group]
                    bank_first_read = sync_point - SimConfig.RL
                    bank_last_read = bank_first_read + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                    bus_start = sync_point
                    bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                    pu_start = sync_point + SimConfig.BL/2
                    pu_end = pu_start + (col_num) * max(SimConfig.tCCDL, SimConfig.BL/2)
                    # bank read
                    for i, pu_id in enumerate(actual_pu_list):
                        self.devices[op1_src_device[i]].banks[op1_bank]\
                            .issue_inst(bank_last_read, op1_row_id, op1_col_offset, col_num, auto_precharge, write=False)
                        self.devices[op1_src_device[i]].bus.set_state(bus_end, bus_start)
                        self.pu[pu_id].set_state(pu_end, pu_start)
                else: 
                    # 假设不使用device间bus，而是device和pu的专属链接
                    op2_src_device = [int(i * pu_connected_device + op2_device) for i in ultilized_pu]
                    sync_point = self.last_cmd_info[inst_group]
                    bank_first_read = sync_point - SimConfig.RL
                    bank_last_read = bank_first_read + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                    bus_start = sync_point
                    bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                    pu_start = sync_point + SimConfig.BL/2
                    pu_end = pu_start + (col_num) * max(SimConfig.tCCDL, SimConfig.BL/2)
                    # bank read
                    for i, pu_id in enumerate(actual_pu_list):
                        self.devices[op1_src_device[i]].banks[op1_bank]\
                            .issue_inst(bank_last_read, op1_row_id, op1_col_offset, col_num, auto_precharge, write=False)
                        self.devices[op2_src_device[i]].banks[op2_bank]\
                            .issue_inst(bank_last_read, op2_row_id, op2_col_offset, col_num, auto_precharge, write=False)
                        self.devices[op1_src_device[i]].bus.set_state(bus_end, bus_start)
                        self.devices[op2_src_device[i]].bus.set_state(bus_end, bus_start)
                        self.pu[pu_id].set_state(pu_end, pu_start)
            # op-level, op-type, ch_id, ra_id, device_mask(并口写入), (bank, row_id, col_offset), col_num, auto_precharge
            # NOTE: 先按照有转化来做
            elif inst[1] == OPTYPE.bk2gb:
                # decode
                device_mask = inst[4]
                bank_id = inst[5]
                row_id = inst[6]
                col_id = inst[7]
                gd_addr = inst[8]
                col_num = inst[9]
                auto_precharge = inst[10]
                device_list = [i for i in range(len(device_mask)) if device_mask[i]]
                # sync point: the first data read from device
                sync_point = self.last_cmd_info[inst_group]
                bank_first_read = sync_point - SimConfig.RL
                bank_last_read = bank_first_read + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                bus_start = sync_point
                bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                buffer_start = sync_point + SimConfig.BL/2
                buffer_end = buffer_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.ra_gb_wl
                # bank read
                for device_id in device_list:
                    self.devices[device_id].banks[bank_id]\
                        .issue_inst(bank_last_read, row_id, col_id, col_num, auto_precharge, write=False)
                    self.devices[device_id].bus.set_state(bus_end, bus_start)
                    self.device_buses[device_id].set_state(bus_end, bus_start)
                # gb write
                self.buffer.set_state(buffer_end, buffer_start)
            elif inst[1] == OPTYPE.gb2bk:
                # decode
                device_mask = inst[4]
                bank_mask = inst[5]
                row_id = inst[6]
                col_id = inst[7]
                gd_addr = inst[8]
                col_num = inst[9]
                auto_precharge = inst[10]
                device_list = [i for i in range(len(device_mask)) if device_mask[i]]
                bank_list = [i for i in range(len(bank_mask)) if bank_mask[i]]
                # sync point: the first data read from device
                sync_point = self.last_cmd_info[inst_group]
                bank_first_write = sync_point - SimConfig.WL
                bank_last_write = bank_first_write + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                bus_start = sync_point
                bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                buffer_start = sync_point - SimConfig.ra_gb_rl
                buffer_end = buffer_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                # bank read
                for device_id in device_list:
                    for bank_id in bank_list:
                        self.devices[device_id].banks[bank_id]\
                            .issue_inst(bank_last_write, row_id, col_id, col_num, auto_precharge, write=True)
                    self.devices[device_id].bus.set_state(bus_end, bus_start)
                    self.device_buses[device_id].set_state(bus_end, bus_start)
                # gb write
                self.buffer.set_state(buffer_end, buffer_start)
        else:
            return self.devices[inst[4]].issue_inst(inst, inst_group)

    # def update(self, tick):
    #     for device in self.devices:
    #         device.update(tick)
    #     for device_bus in self.device_buses:
    #         device_bus.update(tick)
    #     self.buffer.update(tick)