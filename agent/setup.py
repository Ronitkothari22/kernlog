from setuptools import find_packages, setup

setup(
    name="kernlog-agent",
    version="0.1.0",
    description="Kernlog host monitoring agent",
    python_requires=">=3.11",
    packages=find_packages(include=["kernlog_agent", "kernlog_agent.*"]),
    install_requires=[
        "psutil==6.1.0",
        "watchdog==6.0.0",
        "PyYAML==6.0.2",
        "requests==2.32.3",
    ],
    entry_points={"console_scripts": ["kernlog-agent=kernlog_agent.main:cli"]},
)
