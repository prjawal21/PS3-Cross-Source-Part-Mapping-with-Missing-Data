import os
import sys
import subprocess
import time


def run_stage(script_name):
    print(f"\n=============================================================")
    print(f" RUNNING: {script_name}")
    print(f"=============================================================")
    
    t0 = time.time()
    result = subprocess.run([sys.executable, script_name], capture_output=False, check=False)
    elapsed = time.time() - t0
    
    if result.returncode != 0:
        print(f"\n[ERROR] {script_name} failed with exit code: {result.returncode}")
        sys.exit(result.returncode)
    else:
        print(f"\n[SUCCESS] {script_name} finished in {elapsed:.2f} seconds.")


def main():
    print("=============================================================")
    print(" STARTING GEARBOX SERVICE MAPPING PIPELINE ORCHESTRATOR")
    print("=============================================================")
    
    pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(pipeline_dir) # Ensure the cwd is correct for execution
    
    stages = [
        "pipeline/stage0_reconcile.py",
        "pipeline/stage1_profile.py",
        "pipeline/stage2_lexical.py",
        "pipeline/stage3_mesh_filter.py",
        "pipeline/stage4_step_citations.py",
        "pipeline/stage5_propose_verify.py",
        "pipeline/stage6_vision.py",
        "pipeline/stage7_output.py",
        "pipeline/stage8_restructure.py",
    ]
    
    start_time = time.time()
    
    for stage in stages:
        run_stage(stage)
        
    total_elapsed = time.time() - start_time
    print(f"\n=============================================================")
    print(f" PIPELINE COMPLETED SUCCESSFULLY IN {total_elapsed:.1f} SECONDS!")
    print(f"=============================================================")

if __name__ == "__main__":
    main()
