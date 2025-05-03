import google.generativeai as genai
import os

class GenAI:
    """
    A class to interact with the Google Generative AI model.

    Uses the gemini-1.5-flash model for text generation.
    Requires the API_KEY environment variable to be set.
    """
    def __init__(self, sys_instruction: str) -> None:
        """
        Initializes the GenAI object.

        Args:
            sys_instruction: The system instruction for the AI model.
        """
        genai.configure(api_key=os.environ['API_KEY'])
        self.generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=self.generation_config,
            safety_settings="BLOCK_NONE",
            system_instruction=sys_instruction,
        )

        self.chat = self.model.start_chat(history=[])

    def send_msg(self, message: str) -> str:
        """
        Sends a message to the chat and returns the response text.

        Args:
            message: The message to send.

        Returns:
            The text of the AI's response.
        """
        response = self.chat.send_message(content=message)
        return response.text

if __name__ == '__main__':
    # Example usage:
    # Ensure API_KEY environment variable is set
    # try:
    #     model = GenAI("You are a helpful assistant.")
    #     response = model.send_msg("Hello, how are you?")
    #     print(response.text)
    # except KeyError:
    #     print("API_KEY environment variable not set.")
    pass # Placeholder for potential future test code