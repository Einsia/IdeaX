from agents import DeepResearchAgent,ReviewAgent,get_llms
import asyncio
import json
import argparse
import yaml
import os
from pathlib import Path
import nest_asyncio
from checkpoints import checkpoint

nest_asyncio.apply()
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)
for key, value in config.items():
    if value is None or value == "" or (isinstance(value, str) and value.startswith("${")):
        continue
    else:
        os.environ[key] = str(value)


if __name__ == '__main__':

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--topic",type=str,help="research topic",default="Using diffusion to generate urban road layout map")
    argparser.add_argument("--topic_file",type=str,help="UTF-8 file containing a long research topic")
    argparser.add_argument("--anchor_paper_path",type=str,help="PDF path of the anchor paper",default= None)
    argparser.add_argument("--save_file",type=str,default="saves/",help="save file path")
    argparser.add_argument("--improve_cnt",type=int,default= 1,help="experiment refine count")
    argparser.add_argument("--max_chain_length",type=int,default=5,help="max chain length")
    argparser.add_argument("--min_chain_length",type=int,default=3,help="min chain length")
    argparser.add_argument("--max_chain_numbers",type=int,default=1,help="max chain numbers")
    
    args = argparser.parse_args()

    main_llm , cheap_llm = get_llms()

    topic = Path(args.topic_file).read_text(encoding="utf-8") if args.topic_file else args.topic
    anchor_paper_path = args.anchor_paper_path


    review_agent = ReviewAgent(save_file=args.save_file,llm=main_llm,cheap_llm=cheap_llm)
    deep_research_agent = DeepResearchAgent(llm=main_llm,cheap_llm=cheap_llm,**vars(args))

    print(f"begin to generate idea and experiment of topic {topic}")
    idea,related_experiments,entities,idea_chain,ideas,trend,future,human,year=  checkpoint("idea", deep_research_agent, lambda: deep_research_agent.generate_idea_with_chain(topic,anchor_paper_path))
    if not idea or not str(idea).strip():
        raise RuntimeError("CoI did not produce a nonempty idea; no successful result will be written")
    experiment = checkpoint("experiment", deep_research_agent, lambda: deep_research_agent.generate_experiment(idea,related_experiments,entities))

    review_stage_prefix = "review_"
    if Path("post_review_source_correction.json").exists():
        # Restore this run's already completed native experiment improvement.
        # Then source correction and one further native review use that result.
        for i in range(args.improve_cnt):
            completed_path = Path(".stage_cache") / ("review_" + str(i) + ".json")
            if not completed_path.exists():
                raise RuntimeError("Post-review correction requires a durable native review checkpoint")
            experiment = checkpoint("review_" + str(i), deep_research_agent,
                lambda: deep_research_agent.improve_experiment(review_agent,idea,experiment,entities))
        review_stage_prefix = "source_corrected_review_"

    source_feedback = Path("source_review_feedback.json")
    if source_feedback.exists():
        idea = checkpoint("source_declaration_correction", deep_research_agent,
            lambda: review_agent.correct_source_declarations(idea, source_feedback.read_text()))

    for i in range(args.improve_cnt):
        experiment = checkpoint(review_stage_prefix + str(i), deep_research_agent, lambda: deep_research_agent.improve_experiment(review_agent,idea,experiment,entities))
        
    print(f"succeed to generate idea and experiment of topic {topic}")
    res = {"idea":idea,"experiment":experiment,"related_experiments":related_experiments,"entities":entities,"idea_chain":idea_chain,"ideas":ideas,"trend":trend,"future":future,"year":year,"human":human}
    with open("result.json","w") as f:
        json.dump(res,f)
