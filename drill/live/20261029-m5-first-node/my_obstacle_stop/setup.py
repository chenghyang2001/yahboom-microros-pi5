from setuptools import find_packages, setup

package_name = 'my_obstacle_stop'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='My first ROS 2 node: stop when an obstacle is within 0.3 m.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'obstacle_stop = my_obstacle_stop.obstacle_stop:main',
        ],
    },
)
