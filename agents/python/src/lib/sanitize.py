from typing import List
from langchain_core.messages import BaseMessage

def sanitize_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Strict sequence sanitizer to prevent OpenAI BadRequestError:
    "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'"
    This also enforces EXACT ordering of ToolMessages to match AIMessage tool_calls,
    and removes duplicate or orphaned ToolMessages.
    """
    
    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        msg_type = getattr(msg, "type", "")
        
        if msg_type == "human" or msg_type == "system":
            sanitized.append(msg)
            i += 1
            
        elif msg_type == "ai":
            # Clone AI message to ensure mutability
            if getattr(msg, "tool_calls", None):
                from langchain_core.messages import AIMessage as LangchainAIMessage
                msg_kwargs = msg.dict()
                msg = LangchainAIMessage(**{k: v for k, v in msg_kwargs.items() if k in ["content", "additional_kwargs", "name", "id", "tool_calls"]})
            
            sanitized.append(msg)
            ai_msg_index_in_original = i
            i += 1
            
            if not getattr(msg, "tool_calls", None):
                continue
                
            # Collect all subsequent ToolMessages until next non-ToolMessage
            tool_messages_buffer = []
            while i < len(messages) and getattr(messages[i], "type", "") == "tool":
                tool_messages_buffer.append(messages[i])
                i += 1
                
            # Now match them up with the AIMessage tool_calls
            tool_call_ids = [tc["id"] for tc in msg.tool_calls]
            
            matched_tool_messages = {}
            for tm in tool_messages_buffer:
                # Keep the FIRST ToolMessage we find for each ID (ignore duplicates)
                if tm.tool_call_id in tool_call_ids and tm.tool_call_id not in matched_tool_messages:
                    matched_tool_messages[tm.tool_call_id] = tm
                    
            # Strip tool calls that have no matching ToolMessage
            valid_tool_calls = [tc for tc in msg.tool_calls if tc["id"] in matched_tool_messages]
            
            if not valid_tool_calls:
                msg.tool_calls = []
                if "tool_calls" in msg.additional_kwargs:
                    del msg.additional_kwargs["tool_calls"]
            else:
                msg.tool_calls = valid_tool_calls
                if "tool_calls" in msg.additional_kwargs:
                    msg.additional_kwargs["tool_calls"] = [
                        tc for tc in msg.additional_kwargs["tool_calls"] 
                        if tc.get("id") in matched_tool_messages
                    ]
            
            # Now append the matched ToolMessages EXACTLY in the order of the (remaining) tool_calls
            for tc in msg.tool_calls:
                if tc["id"] in matched_tool_messages:
                    sanitized.append(matched_tool_messages[tc["id"]])
                    
        elif msg_type == "tool":
            # If we see a ToolMessage OUTSIDE of the loop above, it means it was orphaned
            # (i.e. preceded by a Human/System message, or an AIMessage without tool_calls).
            # We simply drop it.
            i += 1
            
    return sanitized
