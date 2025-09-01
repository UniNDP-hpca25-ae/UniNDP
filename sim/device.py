"""

device:

bank pu
bank (sub-class)
device bus
device buffer

"""
from tools import *
from sim.bank import *
from sim.buffer import *
from sim.PU import *
from math import inf

class Device:

    def __init__(self, channel_id, rank_id, device_id, bankstate, resource_state):
        self.id = (channel_id, rank_id, device_id)
        self.banks = []
        self.bus = Resource(resource_state, 0)
        self.buffer = Buffer(SimConfig.de_gb, resource_state, 1)
        self.ba_num = SimConfig.ba * SimConfig.bg
        self.pu = []
        self.last_cmd_info = {}

        # init banks
        for i in range(self.ba_num):
            self.banks.append(Bank(channel_id, rank_id, device_id, i, bankstate))

        # init PUs
        self.physical_pu_num = max(SimConfig.de_pu)
        for i in range(self.physical_pu_num):
            self.pu.append(PU(resource_state, 2+i))

    def check_inst(self, inst, inst_group):
        assert inst[0] == LEVEL.DE, "inst[0]: %s" % inst[0]
        if inst[1] == OPTYPE.pu:
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            op2_bank = inst[7][0]
            op2_row = inst[7][1]
            op2_col = inst[7][2]
            col_len = inst[8]
            # check
            assert pu_num in SimConfig.de_pu, "pu_num: %d, SimConfig.de_pu: %d" % (pu_num, SimConfig.de_pu)
            pu_connected_bk = self.ba_num/pu_num
            assert op1_bank < pu_connected_bk
            assert op2_bank < pu_connected_bk
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]
            
            if op1_bank == op2_bank: # compute using buffer + bank
                # 在op2的row空间划分本地的输入buffer和device的输入buffer，目前先按照row=0为本地的input buffer
                if op2_row > 0: # compute using gb
                    assert SimConfig.de_gb > 0, "SimConfig.de_gb: %d" % SimConfig.de_gb
                    # sync_point: pu first compute, related to (pu, bank, gb, bus)
                    sync_point = 0
                    for i, pu_id in enumerate(actual_pu_list):
                        pu_sync_point = self.pu[pu_id].check_state()
                        src_1_sync_point = sum( self.banks[op1_src[i]].check_inst(op1_row, write=False) ) + SimConfig.RL
                        sync_point = max(sync_point, pu_sync_point, src_1_sync_point)
                    bus_sync_point = self.bus.check_state()
                    # gb_sync_point = self.buffer.check_inst(write=False) + SimConfig.de_gb_rl
                    gb_sync_point = self.buffer.check_state() + SimConfig.de_gb_rl
                    sync_point = max(sync_point, gb_sync_point, bus_sync_point)
                    # get issue time
                    issue_time = inf
                    for i, pu_id in enumerate(actual_pu_list):
                        pu_issue_time = sync_point
                        src_1_issue_time = sync_point - self.banks[op1_src[i]].check_inst(op1_row, write=False)[1] - SimConfig.RL
                        issue_time = min(issue_time, pu_issue_time, src_1_issue_time)
                    bus_issue_time = sync_point
                    gb_issue_time = sync_point - SimConfig.de_gb_rl
                    issue_time = min(issue_time, gb_issue_time, bus_issue_time)
                    self.last_cmd_info[inst_group] = sync_point
                    return issue_time
                else:
                    # NOTE: Bank-level NMP(UPMEM-like), pu read from self input buffer & related bank
                    assert SimConfig.de_pu_inbuf > 0
                    # sync_point: pu first compute, related to (pu, bank, gb, bus)
                    sync_point = 0
                    for i, pu_id in enumerate(actual_pu_list):
                        pu_sync_point = self.pu[pu_id].check_state()
                        src_1_sync_point = sum( self.banks[op1_src[i]].check_inst(op1_row, write=False) ) + SimConfig.RL
                        sync_point = max(sync_point, pu_sync_point, src_1_sync_point)
                    # get issue time
                    issue_time = inf
                    for i, pu_id in enumerate(actual_pu_list):
                        src_1_issue_time = sync_point - self.banks[op1_src[i]].check_inst(op1_row, write=False)[1] - SimConfig.RL
                        issue_time = min(issue_time, src_1_issue_time)
                    self.last_cmd_info[inst_group] = sync_point
                    return issue_time

            else: # compute using 2 banks
                op2_src = [ int( i * pu_connected_bk + op2_bank) for i in ultilized_pu ]
                # get latency
                sync_point = 0
                for i, pu_id in enumerate(actual_pu_list):
                    pu_sync_point = self.pu[pu_id].check_state() - SimConfig.RL
                    src_1_sync_point = sum( self.banks[op1_src[i]].check_inst(op1_row, write=False) )
                    src_2_sync_point = sum( self.banks[op2_src[i]].check_inst(op2_row, write=False) )
                    sync_point = max(sync_point, pu_sync_point, src_1_sync_point, src_2_sync_point)
                # get issue time
                issue_time = inf
                for i, pu_id in enumerate(actual_pu_list):
                    pu_issue_time = sync_point + SimConfig.RL
                    src_1_issue_time = sync_point - self.banks[op1_src[i]].check_inst(op1_row, write=False)[1]
                    src_2_issue_time = sync_point - self.banks[op2_src[i]].check_inst(op2_row, write=False)[1]
                    issue_time = min(issue_time, pu_issue_time, src_1_issue_time, src_2_issue_time)
                self.last_cmd_info[inst_group] = sync_point
                return issue_time
            
        elif inst[1] in [OPTYPE.reg2buf, OPTYPE.buf2reg]: # happen inside PU
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            # check
            assert pu_num in SimConfig.de_pu, "pu_num: %d, SimConfig.de_pu: %d" % (pu_num, SimConfig.de_pu)
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            # 同步点即为开始更换的时间，PU同步做更新
            sync_point = 0
            for i, pu_id in enumerate(actual_pu_list):
                pu_sync_point = self.pu[pu_id].check_inst(inst[1])
                sync_point = max(sync_point, pu_sync_point)
            self.last_cmd_info[inst_group] = sync_point
            return sync_point
        
        elif inst[1] == OPTYPE.buf2bk:
            # assume that the buffer replace all of its data
            assert SimConfig.de_pu_bf >= SimConfig.co_w
            assert SimConfig.de_pu_bf % SimConfig.co_w == 0
            # col_len = SimConfig.de_pu_bf / SimConfig.co_w
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            is_input, buffer_addr, col_len = inst[7]
            auto_precharge = inst[8]
            if not is_input: # output无法指定col_len?
                col_len = SimConfig.de_pu_bf / SimConfig.co_w
            else:
                assert col_len * SimConfig.co_w <= SimConfig.de_pu_inbuf
            # check
            assert pu_num in SimConfig.de_pu, "pu_num: %d, SimConfig.de_pu: %d" % (pu_num, SimConfig.de_pu)
            pu_connected_bk = self.ba_num/pu_num
            assert op1_bank < pu_connected_bk
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]

            sync_point = 0
            for i, pu_id in enumerate(actual_pu_list):
                pu_sync_point = self.pu[pu_id].check_state() + SimConfig.de_pu_bf_rl
                src_1_sync_point = sum( self.banks[op1_src[i]].check_inst(op1_row, write=True) ) + SimConfig.WL
                sync_point = max(sync_point, pu_sync_point, src_1_sync_point)
            # get issue time
            issue_time = inf
            for i, pu_id in enumerate(actual_pu_list):
                pu_issue_time = sync_point - SimConfig.de_pu_bf_rl
                src_1_issue_time = sync_point - self.banks[op1_src[i]].check_inst(op1_row, write=True)[1] - SimConfig.WL
                issue_time = min(issue_time, pu_issue_time, src_1_issue_time)
            self.last_cmd_info[inst_group] = sync_point
            return issue_time

        elif inst[1] == OPTYPE.bk2buf:
            # assume that the buffer replace all of its data
            assert SimConfig.de_pu_bf >= SimConfig.co_w
            assert SimConfig.de_pu_bf % SimConfig.co_w == 0
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            is_input, buffer_addr, col_len = inst[7]
            auto_precharge = inst[8]
            if not is_input:
                col_len = SimConfig.de_pu_bf / SimConfig.co_w
            # else:
            #     assert col_len * SimConfig.co_w <= SimConfig.de_pu_inbuf, f"col_len: {col_len}, SimConfig.co_w: {SimConfig.co_w}, SimConfig.de_pu_inbuf: {SimConfig.de_pu_inbuf}"
            # check
            assert pu_num in SimConfig.de_pu, "pu_num: %d, SimConfig.de_pu: %d" % (pu_num, SimConfig.de_pu)
            pu_connected_bk = self.ba_num/pu_num
            assert op1_bank < pu_connected_bk
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]

            sync_point = 0
            for i, pu_id in enumerate(actual_pu_list):
                pu_sync_point = self.pu[pu_id].check_state() + SimConfig.de_pu_bf_wl
                src_1_sync_point = sum( self.banks[op1_src[i]].check_inst(op1_row, write=False) ) + SimConfig.RL
                sync_point = max(sync_point, pu_sync_point, src_1_sync_point)
            # get issue time
            issue_time = inf
            for i, pu_id in enumerate(actual_pu_list):
                pu_issue_time = sync_point - SimConfig.de_pu_bf_wl
                src_1_issue_time = sync_point - self.banks[op1_src[i]].check_inst(op1_row, write=False)[1] - SimConfig.RL
                issue_time = min(issue_time, pu_issue_time, src_1_issue_time)
            self.last_cmd_info[inst_group] = sync_point
            return issue_time
        
        elif inst[1] == OPTYPE.bk2gb:
            # DECODE
            bank_id = inst[5]
            bank_row, bank_col_offset = inst[6]
            gb_col_offset = inst[7]
            col_len = inst[8]
            auto_precharge = inst[9]
            # get sync point
            bank_sync_point = sum( self.banks[bank_id].check_inst(bank_row, write=False) ) + SimConfig.RL
            bus_sync_point = self.bus.check_state()
            gb_sync_point = self.buffer.check_state() + SimConfig.de_gb_wl
            sync_point = max(0, bank_sync_point, gb_sync_point, bus_sync_point)
            # get issue time
            bank_issue_time = sync_point - SimConfig.RL - self.banks[bank_id].check_inst(bank_row, write=False)[1]
            bus_issue_time = sync_point
            gb_issue_time = sync_point - SimConfig.de_gb_wl
            issue_time = min(inf, bank_issue_time, gb_issue_time, bus_issue_time)
            self.last_cmd_info[inst_group] = sync_point
            return issue_time


        elif inst[1] == OPTYPE.gb2bk:
            # DECODE
            bank_mask = inst[5]
            assert len(bank_mask) == self.ba_num
            bank_row, bank_col_offset = inst[6]
            gb_col_offset = inst[7]
            col_len = inst[8]
            auto_precharge = inst[9]
            bank_id_list = [ i for i in range(self.ba_num) if bank_mask[i] ]

            # get sync point
            bank_sync_point = 0
            for bank_id in bank_id_list:
                bank_sync_point = max(bank_sync_point, sum( self.banks[bank_id].check_inst(bank_row, write=True) ) + SimConfig.WL)
            # bank_sync_point = sum( self.banks[bank_id].check_inst(bank_row, write=False) ) + SimConfig.RL
            bus_sync_point = self.bus.check_state()
            gb_sync_point = self.buffer.check_state() + SimConfig.de_gb_rl
            sync_point = max(0, bank_sync_point, gb_sync_point, bus_sync_point)
            
            # get issue time
            bank_issue_time = inf
            for bank_id in bank_id_list:
                bank_issue_time = min(bank_issue_time, sync_point - SimConfig.WL - self.banks[bank_id].check_inst(bank_row, write=True)[1])
                # bank_sync_point = min(bank_sync_point, sum( self.banks[bank_id].check_inst(bank_row, write=True) ) + SimConfig.WL)
            bus_issue_time = sync_point
            gb_issue_time = sync_point - SimConfig.de_gb_rl
            issue_time = min(bank_issue_time, gb_issue_time, bus_issue_time)
            self.last_cmd_info[inst_group] = sync_point
            return issue_time
        
        else:
            raise Exception("unknown inst type")

    def issue_inst(self, inst, inst_group):
        assert inst[0] == LEVEL.DE
        if inst[1] == OPTYPE.pu:
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            op2_bank = inst[7][0]
            op2_row = inst[7][1]
            op2_col = inst[7][2]
            col_len = inst[8]
            auto_precharge = inst[9]
            # check
            pu_connected_bk = self.ba_num/pu_num
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]
            if op1_bank == op2_bank:
                if op2_row > 0:
                    # compute using gb
                    assert SimConfig.de_gb > 0, "SimConfig.de_gb: %d" % SimConfig.de_gb
                    # as the sim jump to issue point, use the last_cmd_info to get the sync point
                    sync_point = self.last_cmd_info[inst_group]
                    src_first_read = sync_point - SimConfig.RL
                    src_last_read = src_first_read + (col_len - 1) * SimConfig.pu_lat
                    pu_first_compute = sync_point
                    pu_last_compute = pu_first_compute + (col_len) * SimConfig.pu_lat # pu计时逻辑较为简单，因此强制计算最后一次的时间
                    for i, pu_id in enumerate(actual_pu_list):
                        self.banks[op1_src[i]].issue_inst(src_last_read, op1_row, op1_col, col_len, auto_precharge, write=False)
                        self.pu[pu_id].set_state(pu_last_compute, pu_first_compute)
                    # NOTE: bus seams to be like pu, please check later
                    self.bus.set_state( pu_last_compute, pu_first_compute)
                    #　考虑到需要让buffer持续到PU算完
                    self.buffer.set_state(sync_point - SimConfig.de_gb_rl + col_len * SimConfig.pu_lat, sync_point - SimConfig.de_gb_rl)
                else:
                    assert SimConfig.de_pu_inbuf > 0
                    # compute using bank
                    # as the sim jump to issue point, use the last_cmd_info to get the sync point
                    sync_point = self.last_cmd_info[inst_group]
                    src_first_read = sync_point - SimConfig.RL
                    src_last_read = src_first_read + (col_len - 1) * SimConfig.pu_lat
                    pu_first_compute = sync_point
                    pu_last_compute = pu_first_compute + (col_len) * SimConfig.pu_lat # pu计时逻辑较为简单，因此强制计算最后一次的时间
                    for i, pu_id in enumerate(actual_pu_list):
                        self.banks[op1_src[i]].issue_inst(src_last_read, op1_row, op1_col, col_len, auto_precharge, write=False)
                        self.pu[pu_id].set_state(pu_last_compute, pu_first_compute)
                        
            else:
                # compute using 2 banks
                op2_src = [ int( i * pu_connected_bk + op2_bank) for i in ultilized_pu ]
                # as the sim jump to issue point, use the last_cmd_info to get the sync point
                sync_point = self.last_cmd_info[inst_group]
                src_first_read = sync_point
                src_last_read = src_first_read + (col_len - 1) * SimConfig.pu_lat
                pu_first_compute = sync_point + SimConfig.RL
                pu_last_compute = pu_first_compute + (col_len) * SimConfig.pu_lat

                for i, pu_id in enumerate(actual_pu_list):
                    self.banks[op1_src[i]].issue_inst(src_last_read, op1_row, op1_col, col_len, auto_precharge, write=False)
                    self.banks[op2_src[i]].issue_inst(src_last_read, op2_row, op2_col, col_len, auto_precharge, write=False)
                    self.pu[pu_id].set_state(pu_last_compute, pu_first_compute)
        
        elif inst[1] in [OPTYPE.reg2buf, OPTYPE.buf2reg]:
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            buffer_addr = inst[6]
            if len(inst) == 8:
                end_point = inst[7]
            else:
                end_point = SimConfig.de_pu_bf_wl if inst[1] == OPTYPE.reg2buf else SimConfig.de_pu_bf_rl
            # check
            assert pu_num in SimConfig.de_pu, "pu_num: %d, SimConfig.de_pu: %d" % (pu_num, SimConfig.de_pu)
            sync_point = self.last_cmd_info[inst_group]
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            # 同步点即为开始更换的时间，PU同步做更新
            for i, pu_id in enumerate(actual_pu_list):
                self.pu[pu_id].issue_inst(inst[1], buffer_addr, end_point + sync_point, sync_point)

        elif inst[1] == OPTYPE.buf2bk:
            # assume that the buffer replace all of its data
            assert SimConfig.de_pu_bf >= SimConfig.co_w
            assert SimConfig.de_pu_bf % SimConfig.co_w == 0
            col_len = SimConfig.de_pu_bf / SimConfig.co_w
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            is_input, buffer_addr, col_len = inst[7]
            auto_precharge = inst[8]
            if not is_input:
                col_len = SimConfig.de_pu_bf / SimConfig.co_w
            else:
                assert col_len * SimConfig.co_w <= SimConfig.de_pu_inbuf
            # check
            pu_connected_bk = self.ba_num/pu_num
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]
            # buf -> bank
            # as the sim jump to issue point, use the last_cmd_info to get the sync point
            sync_point = self.last_cmd_info[inst_group]
            src_first_write = sync_point - SimConfig.WL
            src_last_write = src_first_write + (col_len - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
            pu_first_read = sync_point - SimConfig.de_pu_bf_rl
            pu_last_read = pu_first_read + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2) # TODO: check this logic
            for i, pu_id in enumerate(actual_pu_list):
                self.banks[op1_src[i]].issue_inst(src_last_write, op1_row, op1_col, col_len, auto_precharge, write=True)
                self.pu[pu_id].issue_inst(OPTYPE.buf2bk, 0, pu_last_read, pu_first_read)

        elif inst[1] == OPTYPE.bk2buf:
            # assume that the buffer replace all of its data
            assert SimConfig.de_pu_bf >= SimConfig.co_w
            assert SimConfig.de_pu_bf % SimConfig.co_w == 0
            col_len = SimConfig.de_pu_bf / SimConfig.co_w
            # decode
            pu_num = inst[5][0]
            pu_mask = inst[5][1]
            op1_bank = inst[6][0]
            op1_row = inst[6][1]
            op1_col = inst[6][2]
            is_input, buffer_addr, col_len = inst[7]
            auto_precharge = inst[8]
            if not is_input:
                col_len = SimConfig.de_pu_bf / SimConfig.co_w
            # else:
            #     assert col_len * SimConfig.co_w <= SimConfig.de_pu_inbuf            
            # check
            pu_connected_bk = self.ba_num/pu_num
            ultilized_pu = [ i for i in range(pu_num) if pu_mask[i]]
            actual_pu_list = [ int ( i * self.physical_pu_num / pu_num ) for i in ultilized_pu]
            op1_src = [int( i * pu_connected_bk + op1_bank) for i in ultilized_pu]
            # buf -> bank
            # as the sim jump to issue point, use the last_cmd_info to get the sync point
            sync_point = self.last_cmd_info[inst_group]
            src_first_read = sync_point - SimConfig.RL
            src_last_read = src_first_read + (col_len - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
            pu_first_read = sync_point - SimConfig.de_pu_bf_wl
            pu_last_read = pu_first_read + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2) # TODO: check this logic
            for i, pu_id in enumerate(actual_pu_list):
                self.banks[op1_src[i]].issue_inst(src_last_read, op1_row, op1_col, col_len, auto_precharge, write=False)
                self.pu[pu_id].issue_inst(OPTYPE.bk2buf, 0, pu_last_read, pu_first_read)

        elif inst[1] == OPTYPE.bk2gb:
            # DECODE
            bank_id = inst[5]
            bank_row, bank_col_offset = inst[6]
            gb_col_offset = inst[7]
            col_len = inst[8]
            auto_precharge = inst[9]
            
            # get sync point
            sync_point = self.last_cmd_info[inst_group]
            
            # issue command 
            bank_first_read = sync_point - SimConfig.RL
            bank_last_read = bank_first_read + (col_len - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
            self.banks[bank_id].issue_inst(bank_last_read, bank_row, bank_col_offset, col_len, auto_precharge, write=False)

            gb_first_write = sync_point - SimConfig.de_gb_wl
            gb_last_write = gb_first_write + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2)
            # self.buffer.issue_inst(gb_last_write, gb_col_offset, col_len, write=True)
            self.buffer.set_state(gb_last_write, gb_first_write)
            
            bus_start = sync_point
            bus_end = sync_point + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2)
            self.bus.set_state(bus_end, bus_start)

        elif inst[1] == OPTYPE.gb2bk:
            # DECODE
            bank_mask = inst[5]
            assert len(bank_mask) == self.ba_num
            bank_row, bank_col_offset = inst[6]
            gb_col_offset = inst[7]
            col_len = inst[8]
            auto_precharge = inst[9]
            bank_id_list = [ i for i in range(self.ba_num) if bank_mask[i] ]

            # get sync point
            sync_point = self.last_cmd_info[inst_group]
            # issue command
            bank_first_write = sync_point - SimConfig.WL
            bank_last_write = bank_first_write + (col_len - 1) * max(SimConfig.tCCDL, SimConfig.BL/2)
            for bank_id in bank_id_list:
                self.banks[bank_id].issue_inst(bank_last_write, bank_row, bank_col_offset, col_len, auto_precharge, write=True)

            gb_first_read = sync_point
            gb_last_read = gb_first_read + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2)
            self.buffer.set_state(gb_last_read, gb_first_read)

            bus_start = sync_point
            bus_end = sync_point + (col_len) * max(SimConfig.tCCDL, SimConfig.BL/2)
            self.bus.set_state(bus_end, bus_start)

        else:
            raise Exception("unknown inst type")
            

        # clear last_cmd_info
        self.last_cmd_info = {}

    # def update(self, tick):
    #     if tick == 0:
    #         return
    #     # for bank in self.banks:
    #     #     bank.update(tick)
    #     for pu in self.pu:
    #         pu.update(tick)
    #     self.bus.update(tick)
    #     self.buffer.update(tick)