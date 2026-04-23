from setuptools import setup, find_packages

setup(
    name="baykeshop",
    version="1.3.25",
    packages=find_packages(),
    install_requires=[
        "django>=4.2",
        "djangorestframework>=3.15",
        "alipay-sdk-python>=3.7",
        "pillow>=10.0",
    ],
    python_requires=">=3.10",
)
