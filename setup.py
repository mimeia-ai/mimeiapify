from setuptools import setup, find_packages
import os

# Read the contents of README.md for the long description
def read_long_description():
    if os.path.exists("README.md"):
        with open("README.md", "r", encoding="utf-8") as fh:
            return fh.read()
    return ""

setup(
    name='sncl',  # Your package name
    version='1.1.0',  # Version of your package
    packages=find_packages(),  # Automatically find all packages in your project
    install_requires=[
        'requests',  # Add your dependencies here
        'pandas',
        'typing',
        'aiohttp',
        'asyncio'
    ],
    description="A utility library for Airtable API interactions",  # Short description
    long_description=read_long_description(),  # Use README.md as the long description
    long_description_content_type="text/markdown",  # Specify Markdown format for the README
    author='Sasha Nicolai Canal',  # Update with your name
    author_email='sasha@candyflip.co',  # Update with your email
    url='https://github.com/sashanclrp/sncl-personal-libraries',  # Replace with your GitHub repository
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Update if not using MIT
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',  # Minimum Python version requirement
    license="MIT",  # Update if not using MIT
)
