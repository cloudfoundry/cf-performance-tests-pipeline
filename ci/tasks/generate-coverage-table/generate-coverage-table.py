import argparse
import os
import pathlib
import json
import pandas as pd
import tabulate
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates a markdown table showing test coverage of cf-deployment versions')
    parser.add_argument('--results-root-dir', type=pathlib.Path, required=True,
                        help='absolute path to the root of the results directory in the cf-performance-tests-pipeline repo')
    parser.add_argument('--output-file', type=pathlib.Path, required=True,
                        help='absolute path to output file')
    args = parser.parse_args()
    results_dir = args.results_root_dir
    output_file = args.output_file
    filelist = []
    uniqueResults = {}

    for root, dirs, files in os.walk(results_dir):
        for file in files:
            if file.endswith(".json"):
                filelist.append(os.path.join(root,file));

    cf_d_versions = []
    for file in filelist:
        with open(file) as f:
            data = json.load(f)
            cfd_release = data['cfDeploymentVersion']
            cf_d_versions.append(cfd_release)
    
    unique_cf_d_versions = sorted(list(set(cf_d_versions)), reverse=True)
    rows = []
    for version in unique_cf_d_versions:
        row = { 'version': version }
        for combo in ('rails-postgres15','rails-postgres', 'rails-mysql'):
            row[combo] = ':x:'
            for file in filelist:
                path = pathlib.Path(file)
                cc_type = str(os.path.basename(Path(file).parents[4]))
                if 'rails' not in cc_type:
                    raise ValueError(f'expected directory four levels up from results file to be named "rails" but was {cc_type}')
                ccdb = str(os.path.basename(Path(file).parents[3]))
                if 'postgres15' not in ccdb and 'postgres' not in ccdb and 'mysql' not in ccdb:
                    raise ValueError(f'expected directory three levels up from results file to be named "postgres15" or "postgres" or "mysql" but was {ccdb}')
                test_combo = f'{cc_type}-{ccdb}'
                if combo not in f'{cc_type}-{ccdb}':
                    continue
                with open(file) as f:
                    data = json.load(f)
                    if version in data['cfDeploymentVersion']:
                        row[combo] = ':white_check_mark:'
                        break
        rows.append(row)
    
    df = pd.DataFrame(rows)
    with open(output_file, 'w+') as file:
      file.write(df.to_markdown(index=False))
