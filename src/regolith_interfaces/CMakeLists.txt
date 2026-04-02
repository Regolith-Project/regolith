cmake_minimum_required(VERSION 3.8)
project(regolith_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

# Message and service files will be added here as development progresses
# rosidl_generate_interfaces(${PROJECT_NAME}
#   "msg/RoverState.msg"
#   "msg/TraversabilityMap.msg"
#   "msg/LocalisationStatus.msg"
#   "srv/SetWaypoints.srv"
#   DEPENDENCIES std_msgs geometry_msgs sensor_msgs nav_msgs
# )

ament_package()
