import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel

class Output(BaseModel):
    result: int
    explanation: str

def my_tool(x: int) -> int:
    """Returns the square of x."""
    print(f"  [TOOL EXECUTED] Calculating square of {x}")
    return x * x

# Map the function name to the actual callable
tools_map = {
    "my_tool": my_tool
}

def test():
    client = genai.Client()
    
    config = types.GenerateContentConfig(
        temperature=0,
        tools=[my_tool],
        response_mime_type="application/json",
        response_schema=Output.model_json_schema(),
        system_instruction="You are a helpful math assistant. Use the tool to find the square. Then return your final answer as JSON matching the schema."
    )
    
    # 1. Initialize conversation history
    history = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text="What is the square of 5?")]
        )
    ]
    
    print("Starting manual generation loop with generate_content...")
    
    for iteration in range(5): # Limit loop to prevent infinite execution
        print(f"\n--- Iteration {iteration + 1} ---")
        
        # 2. Call generate_content with the entire history
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=history,
            config=config,
        )
        
        # 3. Append the assistant's response to history
        history.append(response.candidates[0].content)
        
        # 4. Check if the model wants to call functions
        if response.function_calls:
            print(f"Model returned {len(response.function_calls)} function call(s).")
            
            tool_response_parts = []
            
            for function_call in response.function_calls:
                name = function_call.name
                args = function_call.args
                print(f"  -> Model requested: {name}({args})")
                
                if name in tools_map:
                    # Execute the local Python function
                    result = tools_map[name](**args)
                    print(f"  -> Tool returned: {result}")
                    
                    # Create the function response part
                    part = types.Part.from_function_response(
                        name=name,
                        response={"result": result}
                    )
                    tool_response_parts.append(part)
                else:
                    print(f"  -> Unknown tool: {name}")
                    part = types.Part.from_function_response(
                        name=name,
                        response={"error": "Tool not found"}
                    )
                    tool_response_parts.append(part)
            
            # 5. Append the tool results to history so the model sees them on the next loop
            history.append(
                types.Content(
                    role="user", # Or 'tool' role if supported, 'user' usually works for tool responses
                    parts=tool_response_parts
                )
            )
            
        else:
            # 6. No function calls means we have the final output!
            print("\nModel produced final text (no function calls).")
            print("FINAL JSON STRING:")
            print(response.text)
            
            # Verify it parses correctly
            try:
                parsed = Output.model_validate_json(response.text)
                print("\nSUCCESSFULLY PARSED INTO PYDANTIC MODEL:")
                print(parsed)
            except Exception as e:
                print(f"Failed to parse: {e}")
                
            break

if __name__ == "__main__":
    test()
