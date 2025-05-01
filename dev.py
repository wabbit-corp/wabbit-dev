#!python3 -X utf8

from typing import Any
import sys
import os
import argparse
from pathlib import Path
import logging

##################################################################################################
# Main
##################################################################################################

type ArgParser = argparse.ArgumentParser
type SubParser = argparse._SubParsersAction[argparse.ArgumentParser]

class Commands:
    def __init__(self, parser: ArgParser) -> None:
        self.root_parser = parser
        self.parsers = {}
        self.subparsers = {}

    class Command:
        def __init__(self, commands: 'Commands', name: str) -> None:
            path = name.split('/')
            parsers = commands.parsers
            subparsers = commands.subparsers

            def subcommand(i: int) -> str:
                if i == 0: return 'command'
                return ('sub' * i) + 'command'

            if '' not in parsers:
                parsers[''] = commands.root_parser

            if '' not in subparsers:
                subparsers[''] = commands.root_parser.add_subparsers(dest='command')
                
            for i in range(1, len(path) + 1):
                p = '/'.join(path[:i])
                p0 = '/'.join(path[:i-1])
                if p not in parsers:
                    parsers[p] = subparsers[p0].add_parser(path[i-1])
                if p not in subparsers and i != len(path):
                    subparsers[p] = parsers[p].add_subparsers(dest=subcommand(i))

            self.parser = parsers[name]

        def __enter__(self) -> 'Commands.Command':
            return self.parser
        
        def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
            pass
        
    def __call__(self, name: str) -> Any:
        return Commands.Command(self, name)

    # check_parser = subparsers.add_parser('check')
    # trufflehog_parser = subparsers.add_parser('trufflehog')
    # publish_parser = subparsers.add_parser('publish')
    # publish_parser.add_argument('project', type=str, nargs='?')
    # test_parser = subparsers.add_parser('test')


async def main() -> None:
    if sys.platform.lower() == "win32":
        os.system('color')
        os.system('chcp 65001 > nul')
        sys.stdout.reconfigure(encoding='utf-8') # type: ignore
        sys.stderr.reconfigure(encoding='utf-8') # type: ignore

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser()
    commands = Commands(parser)

    # deps_parser = subparsers.add_parser('deps')
    # deps_subparsers = deps_parser.add_subparsers(dest='subcommand')
    # deps_subparsers.add_parser('updates')

    with commands('config/check') as cmd:
        pass

    with commands('setup') as cmd:
        cmd.add_argument('--dev', action='store_true')
        cmd.add_argument('--ij', action='store_true')
        
    with commands('llmcopy') as cmd:
        cmd.add_argument('path', type=str, nargs='?')

    with commands('dep/updates') as cmd:
        pass

    with commands('dep/graph') as cmd:
        cmd.add_argument('project', type=str, nargs='?', default='.')
        cmd.add_argument('--projects', action='store_true')
        cmd.add_argument('--graph', action='store_true')
    
    with commands('publish') as cmd:
        cmd.add_argument('project', type=str, nargs='?')

    with commands('jitpack/info') as cmd:
        # jitpack info <group> <artifact> [<version>]
        cmd.add_argument('group', type=str, nargs=1)
        cmd.add_argument('artifact', type=str, nargs=1)
        cmd.add_argument('version', type=str, nargs='?')

    with commands('clean') as cmd:
        cmd.add_argument('project', type=str, nargs='?')

    with commands('status') as cmd:
        cmd.add_argument('project', type=str, nargs=1)

    with commands('commit') as cmd:
        cmd.add_argument('project', type=str, nargs=1)
        cmd.add_argument('message', type=str, nargs=1)

    with commands('push') as cmd:
        cmd.add_argument('project', type=str, nargs='?', default='.')

    with commands('check') as cmd:
        pass

    with commands('trufflehog') as cmd:
        pass

    with commands('test') as cmd:
        pass

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    
    # enable DEBUG logging
    # logging.getLogger().setLevel(logging.DEBUG)
    
    match args.command:
        case 'check-config':
            from dev.tasks.check_config import check_config
            check_config()

        case 'setup':
            from dev.tasks.setup import RepoSetupMode, setup
            if args.ij:    mode = RepoSetupMode.IJ
            elif args.dev: mode = RepoSetupMode.DEV
            else:          mode = RepoSetupMode.PROD
            setup(mode)

        case 'llmcopy':
            from dev.tasks.llmcopy import llmcopy
            llmcopy(Path(args.path))

        case 'jitpack':
            match args.subcommand:
                case 'info':
                    from dev.tasks.jitpack import get_jitpack_info
                    await get_jitpack_info(args.group[0], args.artifact[0], args.version)
                case _:
                    raise ValueError(f"Unknown subcommand: {args.subcommand}")

        case 'dep':
            if args.subcommand == 'updates':
                from dev.tasks.dep_updates import check_for_updates
                check_for_updates()
            elif args.subcommand == 'graph':
                from dev.tasks.dep_graph import get_project_dependencies
                get_project_dependencies(
                    project_name=args.project, 
                    only_projects=args.projects, 
                    include_graph=args.graph)
            else:
                raise ValueError(f"Unknown subcommand: {args.subcommand}")

        case 'publish':
            from dev.tasks.publish import publish_main
            await publish_main(args.project)

        # TODO: review commands below

        case 'clean':
            from dev.review.clean import clean
            clean(args.project)

        case 'status':
            from dev.review.status import status
            project_name = args.project[0]
            path = Path(project_name)
            status(project_name, path)

        case 'commit':
            from dev.review.commit import commit        
            project_name = args.project[0]
            message = args.message[0]
            commit(project_name, message)

        case 'push':
            from dev.review.push import push
            project_name = args.project
            push(project_name)
            project_name = args.project[0]

        case 'check':
            # from dev.review.check import check_unique_identifiers, check
            # check_unique_identifiers()

            for fn in sorted(Path('.').iterdir()):
                if fn.is_dir():
                    if fn.name in ('.git', '.idea', '.llm', '.kotlin', 
                                   '.gradle', '.venv', '.vscode', 'build',
                                   'tmp.jeeves'):
                        continue
                    # print(f'Checking {fn}')
                    if not (fn / '.git').exists():
                        print(f'Not a git repository: {fn}')
                        continue
            
        case 'trufflehog':
            from dev.review.check import trufflehog
            trufflehog()

        case _:
            raise ValueError(f"Unknown command: {args.command}")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())