from distutils.version import StrictVersion
from pathlib import Path

import yaml

if __name__ == '__main__':

    # Can be obtained with `git tag` in `cf-deployment`
    cf_d_versions = ['v16.12.0',
                     'v16.13.0',
                     'v16.14.0',
                     'v16.15.0',
                     'v16.16.0',
                     'v16.17.0',
                     'v16.18.0',
                     'v16.19.0',
                     'v16.20.0',
                     'v16.21.0',
                     'v16.22.0',
                     'v16.23.0',
                     'v16.24.0',
                     'v16.25.0',
                     'v17.0.0',
                     'v17.1.0',
                     'v18.0.0',
                     'v19.0.0',
                     'v20.0.0',
                     'v20.1.0',
                     'v20.2.0',
                     'v20.3.0',
                     'v20.4.0',
                     'v21.0.0',
                     'v21.1.0',
                     'v21.2.0',]

    vars_dir_path = Path(Path.cwd(), "variables")
    cf_d_rerun_vars_path = Path(vars_dir_path, "cf-d-backfill")

    # Remove 'v' for sorting
    for idx, elm in enumerate(cf_d_versions):
        cf_d_versions[idx] = elm[1:]
    cf_d_versions.sort(key=StrictVersion)

    for idx, elm in enumerate(cf_d_versions):
        source = f'v{elm}'
        additional_ops_files = ''

        if idx != len(cf_d_versions)-1:
            target = f'v{cf_d_versions[idx+1]}'
            has_follow_up = True
        else:
            target = None
            has_follow_up = False

        split_version_num = elm.split('.')

        if int(split_version_num[0]) >= 20:
            additional_ops_files = f' operations/speed-up-dynamic-asgs.yml'
        elif int(split_version_num[0]) == 16 and int(split_version_num[1]) <= 14:
            additional_ops_files = f' operations/use-bionic-stemcell-for-addons.yml'

        vars_dict = {
            "cf-d": {
                "source": source,
                "target": target,
                "has-follow-up": has_follow_up,
                "additional-ops-files": additional_ops_files,
            }
        }

        with Path(cf_d_rerun_vars_path, f'v{elm}.yml').open("w") as out:
         yaml.dump(vars_dict, out)



