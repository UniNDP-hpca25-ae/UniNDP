from tools import *
from sim.rank import *
from multiprocessing import Pool
class Channel:
    
    def __init__(self, channel_id, bankstate, resource_state):
        self.ranks = []
        # NOTE: don't model rank buses, as it's a gather all device buses
        self.buffer = []
        self.channel_id = channel_id
        # init ranks
        state_len = resource_state.shape[0]
        state_len_per_rank = state_len // SimConfig.ra
        for rank_id in range(SimConfig.ra):
            self.ranks.append(Rank(channel_id, rank_id, bankstate, resource_state[state_len_per_rank*rank_id:state_len_per_rank*(rank_id+1)]))

    def check_inst(self, inst, inst_group):
        # 筛选Opcode，若与channel侧资源无关则下发给rank
        if inst[0] == LEVEL.CH:
            pass
        else:
            return self.ranks[inst[3]].check_inst(inst, inst_group)
        
    def issue_inst(self, inst, inst_group):
        # 筛选Opcode，若与channel侧资源无关则下发给rank
        if inst[0] == LEVEL.CH:
            pass
        else:
            return self.ranks[inst[3]].issue_inst(inst, inst_group)
        
    # def update(self, tick):
    #     # def update_rank(tick, rank):
    #     #     rank.update(tick)
    #     # _ = Parallel(n_jobs=SimConfig.ra)(delayed(update_rank)(tick, rank) for rank in self.ranks)
    #     for rank in self.ranks:
    #         rank.update(tick)
    #     # print(f"update {tick}")
