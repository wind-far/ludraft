"""Import actual human ratings into a separate report; never alter automatic evidence."""
import argparse
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.evaluation import apply_human_reviews, summary, write_json

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('results',type=Path)
    parser.add_argument('ratings',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('输出文件已存在，请使用新文件保留原证据')
    report=json.loads(args.results.read_text())
    try:apply_human_reviews(report,json.loads(args.ratings.read_text()))
    except ValueError as exc:parser.error(str(exc))
    report['summary']=summary(report)
    write_json(args.output,report)
