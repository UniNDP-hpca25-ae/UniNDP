from tools import *
from collections import deque

class inst_group:
    def __init__(self, id, pre_group, command_queue = []):
        self.id = id
        self.pre_group = pre_group
        self.queue = deque(command_queue)

    # 如果group_list和self.pre_group没有交集，那么可以issue
    def issuable(self, group_list):
        
        # 否则，不能issue
        if not set(group_list).intersection(set(self.pre_group)):
            # 可以issue
            return True
        else:
            # 有重合项，不能issue
            return False
        
    def is_empty(self):
        if self.queue: return False
        else: return True

    # 返回队列中的第一个元素
    def get_inst(self):
        assert not self.is_empty()
        return self.queue[0]
    
    def issue_inst(self):
        assert not self.is_empty()
        self.queue.popleft()

class inst_queue:
    def __init__(self):
        self.groups = {}
        # TODO: 用队列也可以实现同种效果，还是避免使用字典，不是很高效

    def add_group(self, id, pre_group, command_queue = []):
        assert id not in self.groups.keys()
        self.groups[id] = inst_group(id, pre_group, command_queue)

    # return the issuable group
    # @joblib.Parallel
    def issuable_group(self):
        all_group = self.groups.keys()
        issuable_group = []
        for group in all_group:
            if self.groups[group].issuable(all_group):
                issuable_group.append(group)
        return issuable_group

    # 从所有可以issue的group中pop一条指令
    # @joblib.Parallel
    def get_inst(self):
        issuable_group = self.issuable_group()
        inst_list = []
        for group in issuable_group:
            inst = self.groups[group].get_inst()
            inst_list.append(
                (group, inst)
            )
        return inst_list

    # 可优化的点：仲裁决定下一次执行那一条指令

    def issue_inst(self, group_id):
        self.groups[group_id].issue_inst()

    def clear_empty_group(self, group_id):
        if self.groups[group_id].is_empty():
            self.groups.pop(group_id)

    def check_empty(self):
        return len(self.groups) == 0