"""Protocol-level terminal text detection; never a claim that the issue is fixed."""
def terminal_text(raw):
 choices=raw.get('choices',[])
 if len(choices)!=1:return None
 choice=choices[0];message=choice.get('message',{})
 content=message.get('content')
 if (choice.get('finish_reason')=='stop' and message.get('role')=='assistant'
     and not message.get('tool_calls') and not message.get('function_call')
     and not message.get('refusal') and isinstance(content,str) and content.strip()):
  return content
 return None
