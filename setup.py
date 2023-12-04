# Copyright 2023 Navisense GmbH (https://navisense.de)

# This file is part of poeminv.
#
# poeminv is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program, in the file LICENSE at the top level of this
# repository. If not, see <https://www.gnu.org/licenses/>.

import pathlib
import setuptools

requirements_path = (pathlib.Path(__file__).parent / 'requirements').absolute()
with (requirements_path / 'base.txt').open() as f:
    requirements = f.readlines()
with (requirements_path / 'test.txt').open() as f:
    test_requirements = f.readlines()
with (requirements_path / 'dev.txt').open() as f:
    dev_requirements = test_requirements + f.readlines()
with (pathlib.Path(__file__).parent / 'README.md').absolute().open() as f:
    readme = f.read()

setuptools.setup(
    name='poeminv', version='1.0.1',
    description='Tools to create emission inventories for ports.',
    long_description_content_type='text/markdown', long_description=readme,
    author="Navisense GmbH", author_email="support@navisense.de",
    url='https://github.com/Navisense/poeminv', python_requires='>=3.11',
    install_requires=requirements,
    extras_require={'test': test_requirements,
                    'dev': dev_requirements}, license='AGPL-3.0-or-later')
