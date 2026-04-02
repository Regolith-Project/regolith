# Contributing to Regolith

Thank you for your interest in contributing to Regolith! We're building open-source rover autonomy as a commons, and every contribution matters.

## How to Contribute

### Reporting Bugs
- Open an [issue](https://github.com/Regolith-Project/regolith/issues) with a clear description
- Include your ROS 2 distribution, OS version, and steps to reproduce

### Suggesting Features
- Open an issue tagged `enhancement`
- Describe the use case — what problem does this solve for rover autonomy?

### Code Contributions
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Follow the existing code style (C++ follows ROS 2 style guide, Python follows PEP 8)
4. Write tests where applicable
5. Submit a Pull Request with a clear description

### Documentation
Documentation improvements are always welcome — from fixing typos to writing tutorials.

## Development Setup

```bash
# Prerequisites: ROS 2 Humble or Jazzy on Ubuntu 22.04/24.04

git clone https://github.com/Regolith-Project/regolith.git
cd regolith
rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
```

## Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be respectful, constructive, and inclusive.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions?

Open an issue or reach out — we're happy to help you get started.
