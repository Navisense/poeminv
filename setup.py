import pathlib
import setuptools

requirements_path = (pathlib.Path(__file__).parent / 'requirements').absolute()
with (requirements_path / 'base.txt').open() as f:
    requirements = f.readlines()
with (requirements_path / 'test.txt').open() as f:
    test_requirements = f.readlines()
with (requirements_path / 'dev.txt').open() as f:
    dev_requirements = test_requirements + f.readlines()

setuptools.setup(
    name='port-emission-inventory', version='0.1',
    description='Tools to create emission inventories for ports.',
    python_requires='>=3.11', install_requires=requirements,
    extras_require={'test': test_requirements, 'dev': dev_requirements},
    license='AGPL-3.0-or-later')
