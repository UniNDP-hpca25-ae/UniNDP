from tools import *
from sim.channel import * 
from math import inf

class HW_system:
        
    def __init__(self, bankstate, resource_state):
        
        self.host = None
        self.channels = []
        self.channel_dqs = []
        self.PCIe = None # NOTE: 似乎较为高带宽，是否需要对占用sim的更细致一点
        self.last_cmd_info = {}
        # self.bankstate = bankstate
        # divide
        state_len = resource_state.shape[0] - SimConfig.ch
        state_len_per_channel = state_len // SimConfig.ch
        # init channels
        for channel_id in range(SimConfig.ch):
            self.channels.append(Channel(channel_id, bankstate, resource_state[SimConfig.ch+state_len_per_channel*channel_id:SimConfig.ch+state_len_per_channel*(channel_id+1)]))
            self.channel_dqs.append(Resource(resource_state[0:SimConfig.ch], channel_id))
    
    def check_inst(self, inst, inst_group):
        # 筛选Opcode，若与HW_system侧资源无关则下发给channel
        if inst[0] == LEVEL.SYS:
            if inst[1] == OPTYPE.host_read:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                bank_id = inst[5]
                row_id = inst[6]
                col_offset = inst[7]
                col_num = inst[8]
                auto_precharge = inst[9]
                # dram banks involved
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                # find sync point
                sync_point = 0
                for device_id in device_list:
                    bank_sync_point = sum(self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].banks[bank_id]\
                            .check_inst(row_id, write=False)) + SimConfig.RL
                    device_inner_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].check_state()
                    sync_point = max(sync_point, bank_sync_point,\
                                      device_inner_bus_sync_point, device_outer_bus_sync_point)
                # device inner bus / device outer bus / rank bus (same to device bus, ignore) / channel bus
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # find issue point
                issue_time = inf
                for device_id in device_list:
                    bank_issue_time = sync_point - self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].banks[bank_id]\
                            .check_inst(row_id, write=False)[1] - SimConfig.RL
                    issue_time = min(issue_time, bank_issue_time)
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] == OPTYPE.host_write:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                bank_mask = inst[5]
                row_id = inst[6]
                col_offset = inst[7]
                col_num = inst[8]
                auto_precharge = inst[9]
                # dram banks involved
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                bank_list = [i for i in range(SimConfig.ba*SimConfig.bg) if bank_mask[i]]
                # find sync point
                sync_point = 0
                for device_id in device_list:
                    bank_sync_point = 0
                    for bank_id in bank_list:
                        bank_sync_point = max(bank_sync_point, \
                                              sum(self.channels[ch_id].ranks[ra_id] \
                                                .devices[device_id].banks[bank_id] \
                                                    .check_inst(row_id, write=True)) + SimConfig.WL)
                    device_inner_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].check_state()
                    sync_point = max(sync_point, bank_sync_point,\
                                      device_inner_bus_sync_point, device_outer_bus_sync_point)
                # device inner bus / device outer bus / rank bus (same to device bus, ignore) / channel bus
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # TODO: PCIe occupation
                # find issue point
                issue_time = inf
                for device_id in device_list:
                    bank_issue_time = inf
                    for bank_id in bank_list:
                        bank_issue_time = min(bank_issue_time, \
                                              sync_point - self.channels[ch_id].ranks[ra_id]\
                                                .devices[device_id].banks[bank_id]\
                                                    .check_inst(row_id, write=True)[1] - SimConfig.WL)
                    issue_time = min(issue_time, bank_issue_time)
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] == OPTYPE.host_write_device_buffer:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                buffer_addr = inst[5]
                col_num = inst[6]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                # find sync point
                sync_point = 0
                for device_id in device_list:
                    # device buffer write after burst
                    device_buffer_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].buffer.check_state() - SimConfig.BL/2
                    # device inner bus / device outer bus / rank bus (same to device bus, ignore) / channel bus
                    device_inner_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].check_state()
                    sync_point = max(sync_point, device_buffer_sync_point, device_inner_bus_sync_point, device_outer_bus_sync_point)
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # find issue point
                issue_time = sync_point
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] == OPTYPE.host_read_device_buffer:
                pass
            elif inst[1] == OPTYPE.host_write_pu_inbuf:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                pu_mask = inst[5]
                col_offset = inst[6]
                col_num = inst[7]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                # find sync point
                sync_point = 0
                for device_id in device_list:
                    pu_sync_point = 0
                    for pu_id in pu_list:
                        pu_sync_point = max(pu_sync_point, self.channels[ch_id].ranks[ra_id]\
                            .devices[device_id].pu[pu_id].check_state() - SimConfig.BL/2)
                    # device inner bus / device outer bus / rank bus (same to device bus, ignore) / channel bus
                    device_inner_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].check_state()
                    sync_point = max(sync_point, pu_sync_point, device_inner_bus_sync_point, device_outer_bus_sync_point)
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # find issue point
                issue_time = sync_point
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] in [OPTYPE.host_read_mac_reg, OPTYPE.host_write_mac_reg]:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                pu_mask = inst[5]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                
                # TODO: 结果 Register的 Host Read 是否能把总线带宽用满？check if the read can fit in 1 host read
                # 由于我们现在考虑的是比较大的结果 Buffer，可能暂时不会出现单个数据的读出
                # assert SimConfig.co_w >= SimConfig.ba * SimConfig.bg * SimConfig.data_pr
                
                # find sync point
                sync_point = 0
                for device_id in device_list:
                    pu_sync_point = 0
                    for pu_id in pu_list:
                        # 由于reg很小，故而没有读出延迟
                        pu_sync_point = max(pu_sync_point, self.channels[ch_id].ranks[ra_id]\
                            .devices[device_id].pu[pu_id].check_state())
                    # device inner bus / device outer bus / rank bus (same to device bus, ignore) / channel bus
                    device_inner_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.check_state()
                    device_outer_bus_sync_point = self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].check_state()
                    sync_point = max(sync_point, pu_sync_point, device_inner_bus_sync_point, device_outer_bus_sync_point)
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # find issue point
                issue_time = sync_point
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            elif inst[1] in [OPTYPE.host_read_rank_pu_reg, OPTYPE.host_write_rank_pu_reg]:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                rank_pu_mask = inst[4]
                # pu_mask = inst[5]
                rank_pu_list = [i for i in range(SimConfig.ra_pu) if rank_pu_mask[i]]
                # pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                # check if the read can fit in 1 host read
                # assert SimConfig.co_w >= SimConfig.ba * SimConfig.bg * SimConfig.data_pr
                # find sync point
                sync_point = 0
                for rank_pu_id in rank_pu_list:
                    sync_point = max(sync_point, self.channels[ch_id].ranks[ra_id]\
                                        .pu[rank_pu_id].check_state()) # 假设有专用的链接到channel bus上
                    # sync_point = max(sync_point, pu_sync_point)
                sync_point = max(sync_point, self.channel_dqs[ch_id].check_state())
                # find issue point
                issue_time = sync_point
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            # elif inst[1] == OPTYPE.host_write_mac_reg:
            # temporary implement
            else:
                raise Exception("unknown inst type")
        else:
            channel_id = inst[2]
            issue_lat = self.channels[channel_id].check_inst(inst, inst_group)
            return issue_lat
        
    def issue_inst(self, inst, inst_group):
        if inst[0] == LEVEL.SYS:
            if inst[1] == OPTYPE.host_read:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                bank_id = inst[5]
                row_id = inst[6]
                col_offset = inst[7]
                col_num = inst[8]
                auto_precharge = inst[9]
                # dram banks involved
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                # find sync point
                sync_point = self.last_cmd_info[inst_group]
                bank_first_read = sync_point - SimConfig.RL
                bank_last_read = bank_first_read + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                bus_start = sync_point
                bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                for device_id in device_list:
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].banks[bank_id]\
                            .issue_inst(bank_last_read, row_id, col_offset, col_num, auto_precharge, write=False)
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.set_state(bus_end, bus_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].set_state(bus_end, bus_start)
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            elif inst[1] == OPTYPE.host_write:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                bank_mask = inst[5]
                row_id = inst[6]
                col_offset = inst[7]
                col_num = inst[8]
                auto_precharge = inst[9]
                # dram banks involved
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                bank_list = [i for i in range(SimConfig.ba*SimConfig.bg) if bank_mask[i]]
                # find sync point
                sync_point = self.last_cmd_info[inst_group]
                bank_first_write = sync_point - SimConfig.WL
                bank_last_write = bank_first_write + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
                bus_start = sync_point
                bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                for device_id in device_list:
                    for bank_id in bank_list:
                        self.channels[ch_id].ranks[ra_id]\
                            .devices[device_id].banks[bank_id]\
                                .issue_inst(bank_last_write, row_id, col_offset, col_num, auto_precharge, write=True)
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.set_state(bus_end, bus_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].set_state(bus_end, bus_start)
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            elif inst[1] == OPTYPE.host_write_device_buffer:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                buffer_addr = inst[5]
                col_num = inst[6]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                # issue
                sync_point = self.last_cmd_info[inst_group]
                bus_start = sync_point
                # bus_end = bus_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.BL/2
                bus_end = bus_start + (col_num - 1) * SimConfig.BL/2 + SimConfig.BL/2
                buffer_start = sync_point + SimConfig.BL/2
                # buffer_end = buffer_start + (col_num - 1) * max(SimConfig.tCCDL, SimConfig.BL/2) + SimConfig.de_gb_wl
                buffer_end = buffer_start + (col_num - 1) * SimConfig.BL/2 + SimConfig.de_gb_wl                
                # device buffer write
                for device_id in device_list:
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].buffer.set_state(buffer_end, buffer_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.set_state(bus_end, bus_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].set_state(bus_end, bus_start)
                # channel dq
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            elif inst[1] == OPTYPE.host_read_device_buffer:
                pass
            elif inst[1] == OPTYPE.host_write_pu_inbuf:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                pu_mask = inst[5]
                col_offset = inst[6]
                col_num = inst[7]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                # sync_point
                sync_point = self.last_cmd_info[inst_group]
                bus_start = sync_point
                bus_end = bus_start + (col_num - 1) * SimConfig.BL/2 + SimConfig.BL/2
                pu_start = sync_point + SimConfig.BL/2
                pu_end = pu_start + (col_num - 1) * SimConfig.BL/2 + SimConfig.de_pu_bf_wl
                for device_id in device_list:
                    for pu_id in pu_list:
                        self.channels[ch_id].ranks[ra_id]\
                            .devices[device_id].pu[pu_id].set_state(pu_end, pu_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.set_state(bus_end, bus_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].set_state(bus_end, bus_start)
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            elif inst[1] in [OPTYPE.host_read_mac_reg, OPTYPE.host_write_mac_reg]:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                device_mask = inst[4]
                pu_mask = inst[5]
                device_list = [i for i in range(SimConfig.de) if device_mask[i]]
                pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                # sync_point
                sync_point = self.last_cmd_info[inst_group]
                bus_start = sync_point
                bus_end = bus_start + SimConfig.BL/2
                pu_start = sync_point
                pu_end = pu_start + SimConfig.BL/2
                # issue
                for device_id in device_list:
                    for pu_id in pu_list:
                        self.channels[ch_id].ranks[ra_id]\
                            .devices[device_id].pu[pu_id].set_state(pu_end, pu_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .devices[device_id].bus.set_state(bus_end, bus_start)
                    self.channels[ch_id].ranks[ra_id]\
                        .device_buses[device_id].set_state(bus_end, bus_start)
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            elif inst[1] in [OPTYPE.host_read_rank_pu_reg, OPTYPE.host_write_rank_pu_reg]:
                # decode
                ch_id = inst[2]
                ra_id = inst[3]
                rank_pu_mask = inst[4]
                # pu_mask = inst[5]
                rank_pu_list = [i for i in range(SimConfig.ra_pu) if rank_pu_mask[i]]
                # pu_list = [i for i in range(len(pu_mask)) if pu_mask[i]]
                # check if the read can fit in 1 host read
                # sync_point
                sync_point = self.last_cmd_info[inst_group]
                bus_start = sync_point
                bus_end = bus_start + SimConfig.BL/2
                pu_start = sync_point
                pu_end = pu_start + SimConfig.BL/2
                # issue
                for rank_pu_id in rank_pu_list:
                    self.channels[ch_id].ranks[ra_id]\
                        .pu[rank_pu_id].set_state(pu_end, pu_start)
                self.channel_dqs[ch_id].set_state(bus_end, bus_start)
            else:
                raise Exception("unknown inst type")
        else:
            channel_id = inst[2]
            self.channels[channel_id].issue_inst(inst, inst_group)
            # return issue_lat

    # def update(self, tick):
    #     # update all
    #     for channel in self.channels:
    #         channel.update(tick)
    #     for channel_dq in self.channel_dqs:
    #         channel_dq.update(tick)
