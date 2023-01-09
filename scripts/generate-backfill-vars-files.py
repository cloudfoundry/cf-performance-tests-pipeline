from packaging.version import Version
from pathlib import Path
import random
import string

import yaml

if __name__ == '__main__':
    root_branch_cf_perf_tests_pipeline = "v23.0.0"

    # Can be obtained with `git tag -l | sort -V | sed 's/v//g' | xargs -I {} echo \'{}\'` in `cf-deployment`
    cf_deployment_releases = [
                              '23.0.0',
                              '23.1.0',
                              '23.2.0',
                              '23.3.0',
                              '23.4.0',
                              '23.5.0',
                              '24.0.0',
                              '24.1.0',
                              '24.2.0',
                              '24.3.0',
                              '24.4.0',]

    vars_dir_path = Path(Path.cwd(), "variables")
    cf_d_rerun_vars_path = Path(vars_dir_path, "cf-d-backfill")

    cf_deployment_releases.sort(key=Version)

    for idx_ver, cfd_version in enumerate(cf_deployment_releases):
        cfd_version = f'{cfd_version}'
        cfd_version_with_hyphens = cfd_version.replace('.', '-')
        test_name = f'cfd-{cfd_version_with_hyphens}'
        additional_ops_files = ''

        last_test = idx_ver == len(cf_deployment_releases)-1

        if not last_test:
            more_tests = True
            next_cf_d_version_with_hyphens = cf_deployment_releases[idx_ver+1].replace('.', '-')
            next_test = f'cfd-{next_cf_d_version_with_hyphens}'
        else:
            next_test = 'none'
            more_tests = False

        first_test = idx_ver == 0
        if first_test:
            cf_perf_tests_pipeline_source_branch = root_branch_cf_perf_tests_pipeline
        else:
            cf_perf_tests_pipeline_source_branch = f'perf-test-old-{test_name}'

        if Version(cfd_version) <= Version("16.14.0"):
            additional_ops_files += ' operations/use-bionic-stemcell-for-addons.yml'
        if Version(cfd_version) >= Version("20.0.0"):
            additional_ops_files += ' operations/speed-up-dynamic-asgs.yml'

        random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

        vars_dict = {
            "additional-ops-files": additional_ops_files,
            "cloud_controller_type": "rails",
            "cf_deployment_tag_filter": f'v{cfd_version}',
            "cf_router_idle_timeout_secs": "60",
            "cf_perf_tests_pipeline_source_branch": cf_perf_tests_pipeline_source_branch,
            "more_tests": more_tests,
            "next_test_name": next_test,
            "test_suffix": f"-{random_string}"
        }

        with Path(cf_d_rerun_vars_path, f'{test_name}.yml').open("w") as out:
            yaml.dump(vars_dict, out)