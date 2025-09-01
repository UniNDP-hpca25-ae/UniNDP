import enum
from tools import *
import numpy as np

class BankState(enum.Enum):
    IDLE = 1
    ROWOPEN = 2

class Bank(Resource):
    def __init__(self, channel_id, rank_id, device_id, bank_id, bankstate):
        super(Bank, self).__init__(None, None)
        # SimConfig attributes
        self.co = SimConfig.co
        self.ro = SimConfig.ro
        self.co_w = SimConfig.co_w
        # self.data_pr = SimConfig.data_pr
        self.verify = SimConfig.verify
        self.tRCDRD = SimConfig.tRCDRD
        self.tRCDWR = SimConfig.tRCDWR
        self.tRP = SimConfig.tRP
        self.tWTRL = SimConfig.tWTRL
        self.tCCDL = SimConfig.tCCDL
        self.WL = SimConfig.WL
        self.BL = SimConfig.BL
        self.tWR = SimConfig.tWR
        self.tRTPL = SimConfig.tRTPL
        self.RL = SimConfig.RL
        self.tRTRS = SimConfig.tRTRS
        

        self.channel_id = channel_id
        self.rank_id = rank_id
        self.device_id = device_id
        self.bank_id = bank_id
        self.state = BankState.IDLE
        self.openrow = None
        self.nrow = self.ro
        self.ncol = self.co
        # self.ndata = self.co_w / self.data_pr

        # NOTE: timing
        # self.nxt_act = 0
        # self.nxt_pre = 0
        # self.nxt_read = 0
        # self.nxt_write = 0
        self.np_bankstate = bankstate[self.channel_id][self.rank_id][self.device_id][self.bank_id]
        self.row_change_time = 0
        # TODO: 记录换行的情况
        
        if self.verify:
            self.data = []

    # 何时能schedule对应的操作？
    def check_inst(self, target_row, write=False):
        # 占用逻辑维护了最后一条指令的issue时间
        # if write:
        #     # write to bank
        #     if self.state == BankState.IDLE:
        #         # read_cmd_delay = self.nxt_act + self.tRCDRD
        #         first_cmd_delay = self.nxt_act
        #         follwing_cmd_delay = self.tRCDWR
        #     else:
        #         if self.openrow == target_row:
        #             first_cmd_delay = self.nxt_write
        #             follwing_cmd_delay = 0
        #         else:
        #             first_cmd_delay = self.nxt_pre
        #             follwing_cmd_delay = self.tRP + self.tRCDWR
        # else:
        #     # read from bank
        #     if self.state == BankState.IDLE:
        #         # read_cmd_delay = self.nxt_act + self.tRCDRD
        #         first_cmd_delay = self.nxt_act
        #         follwing_cmd_delay = self.tRCDRD
        #     else:
        #         if self.openrow == target_row:
        #             first_cmd_delay = self.nxt_read
        #             follwing_cmd_delay = 0
        #         else:
        #             first_cmd_delay = self.nxt_pre
        #             follwing_cmd_delay = self.tRP + self.tRCDRD
        
        # numpy: ch_id, ra_id, de_id, ba_id, 4(act, pre, read, write)
        if write:
            # write to bank
            if self.state == BankState.IDLE:
                # read_cmd_delay = self.nxt_act + self.tRCDRD
                first_cmd_delay = self.np_bankstate[0]
                follwing_cmd_delay = self.tRCDWR
            else:
                
                if self.openrow == target_row:
                    first_cmd_delay = self.np_bankstate[3]
                    follwing_cmd_delay = 0
                else:
                    # raise Exception("write to bank, openrow != target_row")
                    first_cmd_delay = self.np_bankstate[1]
                    follwing_cmd_delay = self.tRP + self.tRCDWR
        else:
            # read from bank
            if self.state == BankState.IDLE:
                # read_cmd_delay = self.nxt_act + self.tRCDRD
                first_cmd_delay = self.np_bankstate[0]
                follwing_cmd_delay = self.tRCDRD
            else:
                if self.openrow == target_row:
                    first_cmd_delay = self.np_bankstate[2]
                    follwing_cmd_delay = 0
                else:
                    # NOTE: 如果需要检测是否有换行问题，raise Exception("read from bank, openrow != target_row")
                    first_cmd_delay = self.np_bankstate[1]
                    follwing_cmd_delay = self.tRP + self.tRCDRD
        # 返回可以 issue 第一条 read command 的时间
        return first_cmd_delay, follwing_cmd_delay

    # 发射指令
    def issue_inst(self, last_read_write, target_row, col_offset, col_len, auto_precharge, write=False):
        # check range
        assert target_row >= 0
        assert col_len > 0
        assert col_offset >= 0
        # assert target_row < self.nrow
        # assert col_offset + col_len <= self.ncol
        if write:
            if auto_precharge:
                self.state = BankState.IDLE
                self.openrow = None
                # add pre if auto precharge
                last_command = last_read_write + self.WL + self.BL/2 + self.tWR
                # self.nxt_read = 0
                # self.nxt_write = 0
                # self.nxt_pre = 0
                # self.nxt_act = last_command + self.tRP
                # use numpy
                self.np_bankstate[:] = [last_command + self.tRP, 0, 0, 0]
            else:
                self.state = BankState.ROWOPEN
                self.openrow = target_row
                # self.nxt_act = 0
                # self.nxt_pre = last_read_write + self.WL + self.BL/2 + self.tWR
                # self.nxt_read = last_read_write + self.WL + self.BL / 2 + self.tWTRL
                # self.nxt_write = last_read_write + max(self.BL/2, self.tCCDL)
                self.np_bankstate[:] = \
                    np.array([0, last_read_write + self.WL + self.BL/2 + self.tWR,\
                      last_read_write + self.WL + self.BL / 2 + self.tWTRL,\
                          last_read_write + max(self.BL/2, self.tCCDL)], dtype=np.int64)
        else:
            if auto_precharge:
                self.state = BankState.IDLE
                self.openrow = None
                # add pre if auto precharge
                last_command = last_read_write + self.BL/2 + max(self.tRTPL-self.tCCDL, 0)
                # self.nxt_read = 0
                # self.nxt_write = 0
                # self.nxt_pre = 0
                # self.nxt_act = last_command + self.tRP
                self.np_bankstate[:] = [last_command + self.tRP, 0, 0, 0]
            else:
                self.state = BankState.ROWOPEN
                self.openrow = target_row
                # self.nxt_act = 0
                # self.nxt_pre = last_read_write + self.BL/2 + max(self.tRTPL-self.tCCDL, 0)
                # self.nxt_read = last_read_write + max(self.BL/2, self.tCCDL)
                # self.nxt_write = last_read_write + self.RL + self.BL/2 + self.tRTRS - self.WL
                self.np_bankstate[:] = \
                    np.array([0, \
                        last_read_write + self.BL/2 + max(self.tRTPL-self.tCCDL, 0),\
                            last_read_write + max(self.BL/2, self.tCCDL), \
                                last_read_write + self.RL + self.BL/2 + self.tRTRS - self.WL], dtype=np.int64)

    # # 根据操作，更新Bank的状态
    # def update(self, tick):
    #     self.nxt_act = max(self.nxt_act - tick,0)
    #     self.nxt_pre = max(self.nxt_pre - tick,0)
    #     self.nxt_read = max(self.nxt_read - tick,0)
    #     self.nxt_write = max(self.nxt_write - tick,0)
        
""" test bank.py
"""
def test():
    bank = Bank(0, 0, 0, 0)
    bank.col = 100
    print(bank.col)
    print(bank.row)

if __name__ == '__main__':
    test()
