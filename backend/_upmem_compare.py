from math import ceil
from tools import *
from backend.base import BaseCodegen
import numpy as np

class upmem_compare(BaseCodegen):
    def __init__(self, require_power_of_2):
        super(upmem_compare, self).__init__(require_power_of_2)
        # TODO: predictor should be defined
        device_num = SimConfig.de * SimConfig.ra
        rank_num = SimConfig.ra
        self.predictor = np.array([
            0, # 'pu'
            SimConfig.pu_lat/device_num, # 'pu_col'
            (SimConfig.read_row_change_apox-SimConfig.pu_lat)/device_num, # 'pu_row_change'
            1/device_num+1, # 'device_reg2buf'
            1/device_num, # 'device_buf2reg'
            SimConfig.write_row_change_apox/device_num, # 'device_buf2bk' # will auto-precharge
            SimConfig.col_change_apox/device_num, # 'device_buf2bk_col'
            SimConfig.read_row_change_apox/device_num, # 'device_bk2buf' # will auto-precharge
            SimConfig.col_change_apox/device_num, # 'device_bk2buf_col'
            0, # 'device_bk2gb'
            0, # 'device_bk2gb_col'
            0, # 'device_gb2bk'
            0, # 'device_gb2bk_col'
            SimConfig.read_row_change_apox/rank_num, # 'host_read'
            max(SimConfig.tCCDL, SimConfig.BL/2)/rank_num, # 'host_read_col'
            0, # 'host_write'
            0, # 'host_write_col'
            0, # 'host_write_device_buffer'
            0, # 'host_write_device_buffer_col'
            0, # 'host_write_pu_inbuf'
            SimConfig.BL/2/rank_num, # 'host_write_pu_inbuf_col'
            SimConfig.BL/2/rank_num, # 'host_read_mac_reg'
            SimConfig.BL/2/rank_num, # 'host_write_mac_reg'
        ])

    # TODO: code micro for mm operator, aim global buffer
    def mm_micro(self, mm_schedule, base_group_id,
                    channel_list, rank_list, device_list, pu_num, simd_l,
                    input_bank, input_row_offset, weight_bank, weight_row_offset, output_bank, output_row_offset,
                    m_block, k_block, l_block, b_block,
                    m_row, k_row, l_row, b_row, 
                    m_block_corner, k_block_corner, l_block_corner, b_block_corner,
                    om_block, ol_block, ob_block,
                    om_row, ol_row, ob_row,
                    om_block_corner, ol_block_corner, ob_block_corner,
                    pu_m, pu_k, pu_l, pu_b,
                    pu_list, performance_threshold):
        # print('ABC', input_bank, weight_bank, output_bank)
        # hbm-pim有一些输入buffer和一些输出buffer
        input_cols_hold_in_buf = SimConfig.de_pu_inbuf // SimConfig.co_w
        # pu, pu_col, pu_row_change, host_write_pu_inbuf_col
        tmp_inst_groups = []
        cmd_left = performance_threshold
        group_id = base_group_id
        for channel_id in channel_list:
            for rank_id in rank_list:
                device_mask = [i in device_list for i in range(SimConfig.de)]
                tmp_inst_list = []
                pu_mask = [(i in pu_list) for i in range(pu_num)]
                # row loop m-k-l, col loop m-l-k (fixed, best for output change)
                if mm_schedule == 'mkl':
                    for m_row_id in range(m_row):
                        for k_row_id in range(k_row):
                            # consider corner case
                            k_block_real = k_block if k_row_id < k_row - 1 else k_block_corner
                            m_block_real = m_block if m_row_id < m_row - 1 else m_block_corner
                            # get the row id in input & weight
                            input_row_id = k_row_id + m_row_id * k_row
                            # compute length
                            col_len = k_block_real
                            if col_len > input_cols_hold_in_buf:
                                # NOTE: overhead of changing input buffer is far more than the overhead of changing weight row
                                
                                # 还是按顺序把一行给做完，但是每次k可能得update多次
                                input_reload_time = ceil(col_len / input_cols_hold_in_buf)
                                last_reload_col_num = col_len - (input_reload_time - 1) * input_cols_hold_in_buf
                                # loop over the block with the row fixed
                                for m_block_id in range(m_block_real):
                                    """
                                        1. 输入搬移逻辑维护，从Host端把数写进来，可能得给各个Bank都写入一遍，但是共享输入的bank可以广播
                                    """
                                    for input_reload_iter in range(input_reload_time): # k维度上的reload
                                        
                                        # reload的k维度大小
                                        k_reload_len = input_cols_hold_in_buf if input_reload_iter < input_reload_time - 1 else last_reload_col_num                                                
                                        
                                        # 写入时存在部分的PU可以复用输入
                                        for input_group in range(pu_m*pu_k):
                                            bank_per_pu = self.bank_num // pu_num
                                            limited_pu_list = pu_list[input_group*pu_l:(input_group+1)*pu_l]
                                            limited_pu_mask = [(i in limited_pu_list) for i in range(pu_num)]
                                            # device并行的写入pu的输入buffer
                                            tmp_inst_list.append(
                                                self.create_host_write_pu_inbuf(
                                                    channel_id, rank_id, device_mask, limited_pu_mask,
                                                    0, k_reload_len
                                                )
                                            )

                                        for l_row_id in range(l_row):
                                            l_block_real = l_block if l_row_id < l_row - 1 else l_block_corner
                                            weight_row_id = l_row_id + k_row_id * l_row
                                            """
                                                2. 计算和输出缓存逻辑维护
                                            """
                                            for l_block_id in range(l_block_real):
                                                # 2. 
                                                input_col_offset = m_block_id * k_block_real + 0
                                                weight_col_offset = l_block_id * k_block_real + 0
                                                # k_block_complete = input_reload_iter == input_reload_time - 1
                                                # input_rowchange = k_block_complete and (m_block_id == m_block_real - 1)
                                                weight_rowchange = (l_block_id == l_block_real - 1)
                                                # 5. 
                                                om_id = m_block_id + m_row_id * m_block
                                                ol_id = l_block_id + l_row_id * l_block
                                                # get l position in output
                                                ol_col_flat_id = ol_id // simd_l
                                                ol_col_id = ol_col_flat_id % ol_block
                                                ol_row_id = ol_col_flat_id // ol_block
                                                
                                                # get l position in output
                                                om_col_flat_id = om_id
                                                om_col_id = om_col_flat_id % om_block
                                                om_row_id = om_col_flat_id // om_block
                                                
                                                # get the col & row of output point
                                                o_col_id = om_col_id * ol_block + ol_col_id
                                                o_row_id = om_row_id * ol_row + ol_row_id
                                            
                                                tmp_inst_list.append(self.create_host_write_mac_reg(
                                                    channel_id, rank_id, device_mask, pu_mask
                                                ))
                                                # for device_id in device_list:
                                                #     # load in result from buffer
                                                #     tmp_inst_list.append(self.create_device_buf2reg(
                                                #         channel_id, rank_id, device_id, pu_num, pu_mask, 0
                                                #     ))
                                                for device_id in device_list:
                                                    # compute 
                                                    tmp_inst_list.append(self.create_device_pu(
                                                        channel_id, rank_id, device_id, pu_num, pu_mask, 
                                                        (weight_bank, weight_row_offset + weight_row_id, weight_col_offset), 
                                                        (weight_bank, 0, input_col_offset), 
                                                        col_len, weight_rowchange
                                                    ))
                                                # # 更换回buffer对应位置
                                                # for device_id in device_list:
                                                #     tmp_inst_list.append(self.create_device_reg2buf(
                                                #         channel_id, rank_id, device_id, pu_num, pu_mask, 0
                                                #     ))
                                                tmp_inst_list.append(self.create_host_read_mac_reg(
                                                    channel_id, rank_id, device_mask, pu_mask
                                                ))
                                                # check the command threshold
                                                # check the command threshold
                                                # if len(tmp_inst_list) > cmd_left:
                                                #     return None, 0, 0
                                        # call the predictor 
                                        if not self.gen_code:
                                            predicted_ = np.dot(self.inst_count, self.predictor)
                                            outer_loop_left_ = input_reload_time * \
                                                ((m_row - 1)*m_block + m_block_corner) * k_row
                                            read_out_latency = om_row * ol_row * SimConfig.read_row_change_apox + \
                                                ((om_row - 1) * om_block + om_block_corner) * ((ol_row - 1) * ol_block + ol_block_corner) * SimConfig.col_change_apox
                                            return {}, predicted_ * outer_loop_left_ + read_out_latency * len(pu_list)
                                                
                            else:
                                m_block_in_a_reload = input_cols_hold_in_buf // k_block_real
                                # loop over the block with the row fixed
                                for m_block_id in range(m_block_real):
                                    if m_block_id % m_block_in_a_reload == 0:
                                        reload_m_len = min(m_block_in_a_reload, m_block_real - m_block_id)
                                        reload_col_len = reload_m_len * k_block_real # NOTE: 写入input buffer的列长
                                        for input_group in range(pu_m*pu_k):
                                            bank_per_pu = self.bank_num // pu_num
                                            limited_pu_list = pu_list[input_group*pu_l:(input_group+1)*pu_l]
                                            # bank_list = [ i * bank_per_pu + input_bank for i in limited_pu_list]
                                            # bank_mask = [( i in bank_list ) for i in range(self.bank_num)]
                                            limited_pu_mask = [(i in limited_pu_list) for i in range(pu_num)]
                                            # device并行的写入pu的输入buffer
                                            tmp_inst_list.append(
                                                self.create_host_write_pu_inbuf(
                                                    channel_id, rank_id, device_mask, limited_pu_mask,
                                                    0, reload_col_len
                                                )
                                            )
                                    for l_row_id in range(l_row):
                                        l_block_real = l_block if l_row_id < l_row - 1 else l_block_corner
                                        weight_row_id = l_row_id + k_row_id * l_row
                                        for l_block_id in range(l_block_real):
                                            input_col_offset = m_block_id * k_block_real
                                            weight_col_offset = l_block_id * k_block_real
                                            # determine precharge
                                            # input_rowchange = (m_block_id == m_block_real - 1)
                                            weight_rowchange = (l_block_id == l_block_real - 1)
                                            # get output id
                                            om_id = m_block_id + m_row_id * m_block
                                            ol_id = l_block_id + l_row_id * l_block
                                            # get l position in output
                                            ol_col_flat_id = ol_id // simd_l
                                            ol_col_id = ol_col_flat_id % ol_block
                                            ol_row_id = ol_col_flat_id // ol_block
                                            # get l position in output
                                            om_col_flat_id = om_id
                                            om_col_id = om_col_flat_id % om_block
                                            om_row_id = om_col_flat_id // om_block
                                            # get the col & row of output point
                                            o_col_id = om_col_id * ol_block + ol_col_id
                                            o_row_id = om_row_id * ol_row + ol_row_id
                                            # load in result from buffer
                                            tmp_inst_list.append(
                                                self.create_host_write_mac_reg(
                                                    channel_id, rank_id, device_mask, pu_mask
                                                )
                                            )
                                            for device_id in device_list:
                                                tmp_inst_list.append(self.create_device_pu(
                                                    channel_id, rank_id, device_id, pu_num, pu_mask, 
                                                    (weight_bank, weight_row_offset + weight_row_id, weight_col_offset), 
                                                    (weight_bank, 0, input_col_offset), 
                                                    col_len, weight_rowchange
                                                ))
                                            tmp_inst_list.append(
                                                self.create_host_read_mac_reg(
                                                    channel_id, rank_id, device_mask, pu_mask
                                                )
                                            )
                                    # call the predictor 
                                    if not self.gen_code:
                                        self.predictor[19] = self.predictor[19] / m_block_in_a_reload
                                        self.predictor[20] = self.predictor[20] / m_block_in_a_reload
                                        predicted_ = np.dot(self.inst_count, self.predictor)
                                        outer_loop_left_ = ((m_row - 1)*m_block + m_block_corner) * k_row
                                        read_out_latency = om_row * ol_row * SimConfig.read_row_change_apox + \
                                            ((om_row - 1) * om_block + om_block_corner) * ((ol_row - 1) * ol_block + ol_block_corner) * SimConfig.col_change_apox
                                        return {}, predicted_ * outer_loop_left_ + read_out_latency * len(pu_list)
                
                elif mm_schedule == 'kml':
                    pass
                
                tmp_inst_groups.append((group_id, [], tmp_inst_list))
                group_id += 1
                cmd_left -= len(tmp_inst_list)
            break
        # if performance_threshold < inf:
        return tmp_inst_groups, performance_threshold - cmd_left