import argparse
from pathlib import Path
from .modules.anonymize import build_prompt_payload, build_result_payload, restore_text
from .modules.reporter import write_prompt_file, write_result_file
from .modules.utils import load_json


def anonymize_command(args):
    content = {'text': args.text}
    source_id = f'prompt_{args.template.replace(" ", "_")}_{args.generated_id}'
    payload = build_prompt_payload(args.template, content, source_id)
    write_prompt_file(Path(args.output), payload)
    print(f'Wrote prompt JSON to {args.output}')


def convert_command(args):
    raw_text = Path(args.input).read_text(encoding='utf-8')
    result_payload = build_result_payload(args.source_id, raw_text, args.reviewer)
    write_result_file(Path(args.output), result_payload)
    print(f'Converted ChatGPT output to JSON: {args.output}')


def restore_command(args):
    result = load_json(Path(args.result))
    metadata = load_json(Path(args.restore_metadata))
    restored_text = restore_text(result.get('result_text', ''), metadata.get('restore_map', {}))
    Path(args.output).write_text(restored_text, encoding='utf-8')
    print(f'Restored text written to {args.output}')


def main():
    parser = argparse.ArgumentParser(description='Anonymizer CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)

    anonymize_parser = subparsers.add_parser('anonymize')
    anonymize_parser.add_argument('--template', required=True)
    anonymize_parser.add_argument('--generated-id', default='0001')
    anonymize_parser.add_argument('--text', required=True)
    anonymize_parser.add_argument('--output', default='prompt.json')
    anonymize_parser.set_defaults(func=anonymize_command)

    convert_parser = subparsers.add_parser('convert')
    convert_parser.add_argument('--input', required=True, help='ChatGPT 出力テキストを含むファイル')
    convert_parser.add_argument('--source-id', required=True, help='元の prompt JSON の id')
    convert_parser.add_argument('--reviewer', default='unknown')
    convert_parser.add_argument('--output', default='result.json')
    convert_parser.set_defaults(func=convert_command)

    restore_parser = subparsers.add_parser('restore')
    restore_parser.add_argument('--result', required=True)
    restore_parser.add_argument('--restore-metadata', required=True)
    restore_parser.add_argument('--output', default='restored.txt')
    restore_parser.set_defaults(func=restore_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
