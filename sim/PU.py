from tools import *

class PU(Resource):
    # 此处pu buffer的占用也视为PU的占用，因此不做区分的资源管理
    def __init__(self, numpy_object, index):
        super().__init__(numpy_object, index)
        # TODO: 可以容纳多少个数据，为了避免从 DRAM 读取的带宽浪费，这个大小需要转化为n个 DRAM 列这个量级
        # self.buffer_size = SimConfig.de_pu_bf / SimConfig.data_pr
        self.buffer_rl = SimConfig.de_pu_bf_rl
        self.buffer_wl = SimConfig.de_pu_bf_wl

        if SimConfig.verify:
            self.buffer_data = []

    def check_inst(self, inst_type):
        if inst_type == OPTYPE.reg2buf:
            pass
        elif inst_type == OPTYPE.buf2reg:
            pass
        elif inst_type == OPTYPE.buf2bk:
            pass
        elif inst_type == OPTYPE.bk2buf:
            pass
        return self.check_state()
            
    def issue_inst(self, inst_type, buffer_addr, countdown, delay):
        # assert not self.occupy
        if inst_type == OPTYPE.reg2buf:
            pass
            # assert buffer_addr < self.buffer_size, "buffer_addr: %d, buffer_size: %d" % (buffer_addr, self.buffer_size)
        elif inst_type == OPTYPE.buf2reg:
            pass
            # assert buffer_addr < self.buffer_size, "buffer_addr: %d, buffer_size: %d" % (buffer_addr, self.buffer_size)
        elif inst_type == OPTYPE.buf2bk:
            pass
        elif inst_type == OPTYPE.bk2buf:
            pass
        self.set_state(countdown, delay)