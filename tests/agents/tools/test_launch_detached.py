import pytest

from miniclaw.agents.tools import launch_detached

@pytest.mark.asyncio
async def test_launch_detached():
    response = await launch_detached(
        cwd="D:\\wormsleep\\workspace\\rpa-platform\\rpa-platform-3.2.3\\rpa-xyz-idea",
        cmd='mvn spring-boot:run -Dspring-boot.run.jvmArguments=\"-Dfile.encoding=UTF-8\"',
        log_file="D:\\logs\\rpa-platform\\rpa-xyz-idea-20260508.log"
    )

    print(response)