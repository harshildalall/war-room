import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context, Model
import httpx

class ParseRequest(Model):
    case_id: str
    file_urls: list
    patient_narrative: str

class ParseResult(Model):
    case_id: str
    status: str
    denial_intake: dict
    missing_info_request: dict
    personal_evidence_task: dict
    external_evidence_task: dict

parser_agent = Agent(
    name="counterclaim_parser",
    seed="counterclaim_parser_seed_change_this",
    port=8002,
    endpoint=["http://localhost:8002/submit"]
)

FASTAPI_URL = "http://localhost:8001/run"

@parser_agent.on_message(model=ParseRequest)
async def handle_parse_request(ctx: Context, sender: str, msg: ParseRequest):
    ctx.logger.info(f"Received parse request for case {msg.case_id}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = []
            for url in msg.file_urls:
                file_response = await client.get(url)
                filename = url.split("/")[-1].split("?")[0]
                files.append(("files", (filename, file_response.content, "application/pdf")))

            response = await client.post(
                FASTAPI_URL,
                files=files,
                data={"patient_narrative": msg.patient_narrative}
            )
            result = response.json()

        await ctx.send(sender, ParseResult(
            case_id=msg.case_id,
            status="success",
            denial_intake=result.get("denial_intake", {}),
            missing_info_request=result.get("missing_info_request", {}),
            personal_evidence_task=result.get("personal_evidence_task", {}),
            external_evidence_task=result.get("external_evidence_task", {})
        ))

    except Exception as e:
        ctx.logger.error(f"Parse failed: {e}")

if __name__ == "__main__":
    parser_agent.run()
