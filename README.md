# 0. Setup

<!-- ## Download the repo -->

```bash
# download the repo
git clone git@github.com:UniNDP-hpca25-ae/UniNDP.git
# enter the repo
cd UniNDP
# install requirements
pip install -r requirements.txt
```

<!-- ## Requirements

- OS: Linux Ubuntu.
- Python, PyYAML, numpy, tqdm, csv. -->


<!-- ## Download the results

> Some of the compilation process is time-comsuming, if you want to skip part of the workload compilation process, you can download the results from the following link.

```bash

``` -->

# 1. Documention

> You can skip this section if you are not interested in the detailed usage of the compiler.

## 1.1 Compiler Usage

### Compile a single operator

```bash
python compile.py -A {architecture_name} -W {workload_type} -S {input_size, reduce_size, output_size, batch_size} -O {output_dir}
```

You can use `-h` option to see the detailed usage of the compiler.

```bash
python compile.py -h
```

### Compile using bash script

#### Step 0: prepare the workload csv

Go to the `workload` dir, we have provided some workload files for you to compile. You can also create your own workload file following the format description in the `workload/README.md`.

#### Step 1: run the script

Choose the workload file and architecture configuration you want to compile, and run the following bash command.

```bash
cd UniNDP
./process_workload.sh {workload_file_name} {architecture_name} {workspace_name}
```
This bash command will compile the workloads on the specified architecture configuration, which will issue a bunch of `nohup xxx &` commands on the background. The output log will all be stored to `nohup.out` file.

#### Step 2: How to monitor and terminate the compile commands issued by the script ?

To monitor the issued compile commands, you can use commands like
```bash
watch 'ps -aux | grep compile'
```

To kill certain background process, you can use commands like
```bash
kill -9 $(ps -aux | grep compile | grep -v grep | awk '{print $2}')
```

#### Step 3: Export the results

After all the workloads are compiled, the result csv and log file will be stored in `./{workspace_name}/{workload_name}_{architecture_name}/csv` and `./{workspace_name}/{workload_name}_{architecture_name}/log` respectively. 

You can use `combine_op.sh` under `./workload` to automatically create results csv files under `./{workspace_name}`, see [2.1]() for more details.

Besides, you can also use `combine_e2e.sh` to directly export the end-to-end results into a single csv file, see [2.2]() for more details.

## 1.2 simulator usage

please refer to `UniNDP/testsim.py` for the usage of the simulator.

## 1.3 Adding a new architecture

- Directly modify the configuration file under `UniNDP/config` if you want to explore different architecture settings on existing computation dataflow. 
- To explore a new dataflow, you should copy `UniNDP/backend/_template.py` to add a new backend, which requires further efforts.


# 2. Artifact Evaluation

## 2.1 MM & MVM Experiment (Sec.VII-B, Table V & VI)

### Step 1: run the bash script (~ 2.5 hours)
```bash
# [under the UniNDP dir]
bash ./process_workload.sh mm.csv {arch} {topK} op # command format
bash ./process_workload.sh mm.csv aim 30 op # example: compile the mm on AiM architecture, select top 30 results to simulate
```

- `{arch}`: Arch 1-5 corresponds to `upmem`, `aim`, `aim8`, `hbm-pim`, `dimmining`.
- `{topK}`: optional, how many compilation results are selected to be simulated, default = 30.
- [How to monitor and terminate the commands issued by the script?](#step-2-how-to-monitor-and-terminate-the-compile-commands-issued-by-the-script)
- Output csv, result log files, and program progress will be stored in `op` folder.

### Step 2: export the results for each architecture

After all the workloads are compiled, run the following command to export the results into csv.

```bash
# [under the UniNDP dir]
cp script/combine_op.sh op/ # copy the combine script to the e2e dir
cd op
bash combine_op.sh
```

For each architecture `{arch}`, the results will be stored in `./op/mm_{arch}.csv`.

## 2.2 End-to-End Experiment (Sec.VII-B, Fig. 7 & 8)


### Step 1: run the bash script
```bash
# [under the UniNDP dir]
bash ./process_workload.sh {workload_filename} {arch} {topK} e2e # command format
bash ./process_workload.sh resnet_18_224.csv aim 30 e2e # example: compile the resnet on AiM architecture, select top 30 results to simulate
```

- `{workload_filename}`: The workload file you want to compile, choose from `resnet_18_224.csv`, `vgg11_224.csv`, `llama2_7B_decode_tk32.csv`, `llama2_7B_prefill.csv`, `llama2_13B_decode_tk32.csv`, `llama2_13B_prefill.csv`.
- `{arch}`: Arch 1,2,5 corresponds to `upmem`, `aim`, `dimmining`.
- `{topK}`: optional, how many compilation results are selected to be simulated, default = 30.
- [How to monitor and terminate the commands issued by the script?](#step-2-how-to-monitor-and-terminate-the-compile-commands-issued-by-the-script)
- Output csv and log files will be stored in `e2e` folder.

### Step 2: export the end-to-end results (Fig.7)

After all the workloads are compiled, run the following command to export the results into csv.

```bash
# [under the UniNDP dir]
cp script/combine_e2e.sh e2e/ # copy the combine script to the e2e dir
cd e2e
bash combine_e2e.sh
```

Then the results will be summarized in `e2e/combined_results.csv`.

### Step 3: Look into the key metrics of compilation results (Fig.8)

The key metrics of the compilation results can also be found in the CSV files. Here are their corresponding names in the CSV files:
- #instructions: `cmd`
- #DRAM-Access-cmd: `pu_dram_access` + `host_dram_access`
- #DRAM-Row-change: `row_change`

## 2.3 Simulator Verification (Sec.VII-C)

In this section, we use MVM operator of {input_size} and {output_size} as example.

**! Warn: as the Samsung simulator can only support workload size which is a multiple of 4096, please make sure the input_size and output_size are multiples of 4096.**

### UniNDP Simulation

```bash
python sim_verify.py -S {input_size} {output_size}
```

Results and the latency of simulation will be reported in `verify_result/log/[input_size, output_size].log`.

### Samsung PIMSimulator Setup & Simulation

> Samsung Simulator: https://github.com/SAITPublic/PIMSimulator/tree/dev

Download this repo using `git clone`, and install the dependencies in 3.1.
Then try the `scons` command in 3.2 to build the simulator. If no error occurs, stop at 3.2 and continue with the steps in the next paragraph.

Then go to the `PIMSimulator/src/tests/PIMBenchTestCases.cpp` file, and change the gemv test case defined at `line 23` into:

```cpp
TEST_F(PIMBenchFixture, gemv)
{
    setPIMBenchTestCase(KernelType::GEMV, {output_size}, {input_size}); // change the input_size and output_size here
    executePIMKernel();
}
```

Then run the following commands to compile and simulate:

```bash
# [under the PIMSimulator dir]
# compile the test
scons
# run the test
./sim --gtest_filter=PIMBenchFixture.gemv > log.txt
```

Results and the latency of simulation will be reported in the `log.txt` file.

## 2.4 Predictor Verification

### Accuracy Verification (Fig.10)

In the paper, we verify the predictor for the following architectures, on the MVM of input size 4096 and output size 4096.

```bash
# [under the UniNDP dir]
python compile_predictor.py -A upmem -S 1 4096 4096 1 -O upmem_pred # Arch 1
python compile_predictor.py -A aim -S 1 4096 4096 1 -O aim_16_pred # Arch 2
python compile_predictor.py -A aim8 -S 1 4096 4096 1 -O aim_8_pred # Arch 3
python compile_predictor.py -A dimmining -S 1 4096 4096 1 -O dimmining_pred # Arch 5
```

This command will generate the result csv in `./test_pred/dimmining_pred/`. You can use predictor results and sim results to verify the accuracy of the predictor.

### Speed Up

If you only want to update the predictor result, use option `-RP` in the command.

```bash
# E.g., enabling -RP on Arch 5
python compile_predictor.py -A dimmining -S 1 4096 4096 1 -O dimmining_pred -RP
```

By enabling and disenabling the `-RP` option, you can compare the speed of the predictor and the simulator.

### Only predictor, no simulation

Also, we can also test the performance of the predictor without simulation, the speedup will decrease from 1.20x to 1.17x.

```bash
# test the performance with predictor and simulation
python -OO compile_predictor.py -A aim -S 4096 4096 4096 1 -O with_sim -Q -K 30
# test the performance with only predictor, no simulation
python -OO compile_predictor.py -A aim -S 4096 4096 4096 1 -O no_sim -Q -K 30 -NS 
```

## 2.5 Pruning Verification

### Pruning Ablation (Fig.9)

This figure is produced by compiling a MVM operator with the size of 1000 on Arch 2, and gradually restrict on the performance upper bound (0.5× and 0.77× of
the highest performance upper bound in the search space).
```Bash
# [Under UniNDP dir]
python compile_detail.py -A aim -S 1 1000 1000 1 -O pruning_test -UU
```

The results will be stored in `UniNDP/pruning_and_breakdown/pruning_test/csv/_gemm.csv`. As it's complicated to draw the figure, the processed excel file for this picture is provided [here](https://drive.google.com/uc?export=download&id=1Ym922wjMMKId5hiNPMbKAsII0sUfS5-9).

### Compilation Speedup

```bash
# test the latency with pruning
python -OO compile_detail.py -A aim -S 4096 4096 4096 1 -O with_prune -Q -K 30
# test the latency w/o pruning
python -OO compile_detail.py -A aim -S 4096 4096 4096 1 -O no_prune -Q -K 30 -UU
```

## 2.6 Breakdown Experiment (Fig.11)

The breakdown figure is draw from the command numbers in the result csv file (as well as the timing parameters in the config file). The processed excel file for this picture is provided [here](https://drive.google.com/uc?export=download&id=1IezYKfBg_NsMSuXNHiFvOuKYDHUvhCti).

```bash
# [under the UniNDP dir]
python -OO compile_detail.py -A upmem -S 4096 6656 832 1 -O upmem_breakdown -Q -K 50 # Arch 1
python -OO compile_detail.py -A aim -S 4096 6656 832 1 -O aim_breakdown -Q -K 50 # Arch 2
python -OO compile_detail.py -A aim8 -S 4096 6656 832 1 -O aim8_breakdown -Q -K 50 # Arch 3
```

## 2.7 Insight 2 (Sec.VII-G-2)

The result in **insight 2** is evaluated by comparing the `best result` (**!!! not the speedup**) of these two input buffer settings on HBM-PIM architecture.
```bash
# use nohup xxx & to run the command in the background

# 4096 MM workload
# 32B input buffer
python compile.py -A hbm-pim -W mm -S 4096 4096 4096 1 -Q -K 5 -IB 256 -O mm_inbuf_256 -WS buffer_insight
# 512B input buffer 
python compile.py -A hbm-pim -W mm -S 4096 4096 4096 1 -Q -K 5 -IB 512 -O mm_inbuf_512 -WS buffer_insight

# 4096 MVM workload
# 32B input buffer
python compile.py -A hbm-pim -W mm -S 1 4096 4096 1 -Q -K 5 -IB 256 -O mvm_inbuf_256 -WS buffer_insight
# 512B input buffer 
python compile.py -A hbm-pim -W mm -S 1 4096 4096 1 -Q -K 5 -IB 512 -O mvm_inbuf_512 -WS buffer_insight
```
