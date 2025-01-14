from setuptools import setup, find_packages
import os

# Read the contents of README.md for the long description (optional)
def read_long_description():
    if os.path.exists("README.md"):
        with open("README.md", "r", encoding="utf-8") as fh:
            return fh.read()
    return ""

packages = find_packages()
print('Packages found:', packages)

setup(
    name='sncl',
    version='0.3',  # Updated version
    packages=packages,
    install_requires=[
        'requests',
        'pandas',
        'typing'
    ],
    description="Sasha Nicolai's utility library for Airtable API interactions",
    long_description=read_long_description(),  # Optional
    long_description_content_type="text/markdown",  # Optional
    author='Sasha Nicolai',
    author_email='sasha@candyflip.co',
    url='https://github.com/sashanclrp/sashanclrp',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Update based on your license
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)