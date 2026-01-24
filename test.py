from llm import get_ai_response

import llm, inspect
print("USING llm.py:", llm.__file__)

question = "논어에서 孝는 개인의 덕목인가, 사회 질서를 위한 기준인가?"
response = get_ai_response(question)

for chunk in response:
    print(chunk, end="")

