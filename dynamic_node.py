import torch
import re
import traceback
from server import PromptServer
from aiohttp import web

class DynamicRuntimeNode:
    is_compiled = False
    
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "code": ("STRING", {"multiline": True, "default": "# INPUTS: model:MODEL, noise:NOISE, cfg:FLOAT, sampler:SAMPLER, sigmas:SIGMAS, positive:CONDITIONING, negative:CONDITIONING, latent:LATENT, target_steps:INT\n# OUTPUTS: diagnostic_latent:LATENT\n\nimport torch\nimport comfy.sample\n\nnoise_obj = inputs[\"noise\"]\nlatent_data = inputs[\"latent\"]\n\nif isinstance(latent_data, dict) and \"samples\" in latent_data:\n latent_tensor = latent_data[\"samples\"]\nelse:\n latent_tensor = latent_data\n\nlatent_dict_wrapper = {\"samples\": latent_tensor}\n\nnoise = noise_obj.generate_noise(latent_dict_wrapper)\n\nsingle_step_sigmas = inputs[\"sigmas\"][0:2]\n\nwith torch.no_grad():\n output_latent = comfy.sample.sample_custom(\n inputs[\"model\"],\n noise,\n inputs[\"cfg\"],\n inputs[\"sampler\"],\n single_step_sigmas,\n inputs[\"positive\"],\n inputs[\"negative\"],\n latent_tensor\n )\n\ndiagnostic_latent = {\"samples\": output_latent}\n\nresult = (diagnostic_latent,)"}),
            },
        }

    RETURN_TYPES = ("*",) 
    RETURN_NAMES = ("output",)
    FUNCTION = "execute"
    CATEGORY = "custom_logic"

    def execute(self, code, **kwargs):
        
        if not DynamicRuntimeNode.is_compiled:
            msg = "Must compile Dynamic Node(s) first"
            
            raise RuntimeError(msg)
            
        env = {
            "inputs": kwargs,
            "torch": torch,
            "__builtins__": __builtins__,
        }
        
        try:
            exec(code, env, env)
            result = env.get("result")
            
            output_match = re.search(r"#\s*OUTPUTS:\s*(.*)", code)
            num_expected = len(output_match.group(1).split(",")) if output_match else 0

            if num_expected == 0: return ()
            
            res_tuple = result if isinstance(result, tuple) else (result,)
            if len(res_tuple) != num_expected:
                raise RuntimeError(f"Number of values in 'result' ({len(res_tuple)}) doesn't match # OUTPUTS ({num_expected})")
            
            return res_tuple
            
        except Exception as e:
            error_msg = traceback.format_exc()
            
            raise RuntimeError(error_msg)
            
    @classmethod
    def IS_CHANGED(s, code, **kwargs):
        import hashlib
        return hashlib.sha256(code.encode()).hexdigest()

@PromptServer.instance.routes.post("/dynamic_node/compile")
async def compile_node(request):
    data = await request.json()
    code = data.get("code", "")
    
    DynamicRuntimeNode.is_compiled = False
    
    try:
        compile(code, '<string>', 'exec')
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
    
    DynamicRuntimeNode.is_compiled = True
    
    input_match = re.search(r"#\s*INPUTS:\s*(.*)", code)
    
    parsed_inputs = []
    if input_match:
        for item in input_match.group(1).split(","):
            if ":" in item:
                name, dtype = item.strip().split(":")
                parsed_inputs.append({"name": name.strip(), "type": dtype.strip().upper()})
            else:
                parsed_inputs.append({"name": item.strip(), "type": "*"})

    output_match = re.search(r"#\s*OUTPUTS:\s*(.*)", code)
    
    output_match = re.search(r"#\s*OUTPUTS:\s*(.*)", code)
    
    parsed_outputs = []
    if output_match:
        for item in output_match.group(1).split(","):
            if ":" in item:
                name, dtype = item.strip().split(":")
                parsed_outputs.append({"name": name.strip(), "type": dtype.strip().upper()})
            else:
                parsed_outputs.append({"name": "output", "type": item.strip().upper()})
    else:
        parsed_outputs = [{"name": "result", "type": "*"}]
    
    return web.json_response({"inputs": parsed_inputs, "outputs": parsed_outputs})

NODE_CLASS_MAPPINGS = {"DynamicRuntimeNode": DynamicRuntimeNode}
NODE_DISPLAY_NAME_MAPPINGS = {"DynamicRuntimeNode": "Dynamic Python Node"}