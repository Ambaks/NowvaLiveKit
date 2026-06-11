"""
OnboardingAgent - Handles new user onboarding (name + email capture)
"""

import logging
import re

from livekit.agents import AgentTask, RunContext
from livekit.agents.llm import function_tool

from auth.user_management import create_user_account
from agent.agents.prompts import ONBOARDING_PROMPT
from agent.agents.shared.base_agent import BaseNovaAgent

logger = logging.getLogger(__name__)


class OnboardingAgent(BaseNovaAgent):
    """Handles new user onboarding: name and email capture with confirmation."""

    def __init__(self, state, userdata) -> None:
        super().__init__(state=state, userdata=userdata, instructions=ONBOARDING_PROMPT)

    async def on_enter(self):
        """Generate onboarding greeting"""
        await self._say(
            "Start the onboarding. Say something like: 'Hey! It's great to meet you, I'm Nova, your AI coach for the Nowva smart rack. What's your first name?'"
        )

    @function_tool
    async def capture_first_name(self, context: RunContext, first_name: str):
        """
        Call this when the user has clearly stated their first name for the FIRST time.
        Extract ONLY the actual name, ignoring filler words like "um", "uh", "like", "my name is".

        Args:
            first_name: The user's first name as they spoke it, without filler words
        """
        self.userdata.temp_first_name = first_name.strip()

        logger.debug(f"[DEBUG] Captured first name: {self.userdata.temp_first_name}")

        # Spell out the name for confirmation (with hyphens)
        spelled_name = "-".join(list(self.userdata.temp_first_name.upper()))

        result = (None, f"You just captured the name '{self.userdata.temp_first_name}'. Now confirm it by spelling it out letter by letter as '{spelled_name}' (with hyphens between letters). Ask if that's correct. Keep it short and natural.")

        self._log_function_call("capture_first_name", {"first_name": first_name}, result)

        return result

    @function_tool
    async def confirm_first_name_correct(self, context: RunContext):
        """
        Call this when the user confirms their name is correct after you spelled it out letter-by-letter.
        Only call this if they expressed agreement (yes, correct, right, sounds good, etc.)
        """
        self.userdata.first_name_confirmed = True

        logger.debug(f"[DEBUG] First name '{self.userdata.temp_first_name}' confirmed by user!")

        return None, "The user confirmed their name is correct. Now ask for their email address. Keep it short and natural."

    @function_tool
    async def first_name_incorrect_retry(self, context: RunContext, corrected_name: str = None):
        """
        Call this when the user indicates their name was NOT correct.

        The user might respond in two ways:
        1. Simple disagreement: "no", "wrong", "that's not right"
           → Set corrected_name to None, and we'll ask again

        2. Disagreement with correction: "no, my name is Bake", "actually it's Tom", "no, it's Sarah"
           → Extract the corrected name and pass it as corrected_name parameter
           → This will immediately capture and confirm the new name

        Args:
            corrected_name: The corrected name if user provided it, None if they just said no
        """
        self.userdata.first_name_retry_count += 1

        logger.debug(f"[DEBUG] First name was incorrect, retry attempt {self.userdata.first_name_retry_count}/{self.userdata.max_retries}")

        if self.userdata.first_name_retry_count >= self.userdata.max_retries:
            return None, "Too many retry attempts. Say something like: 'Having trouble with the name. Let's try text input instead - what's your name?' (This should trigger fallback to text mode)"

        if corrected_name:
            self.userdata.temp_first_name = corrected_name.strip()

            logger.debug(f"[DEBUG] User provided corrected first name: {self.userdata.temp_first_name}")

            spelled_name = "-".join(list(self.userdata.temp_first_name.upper()))

            return None, f"The user corrected their name to '{self.userdata.temp_first_name}'. Now confirm it by spelling it out letter by letter as '{spelled_name}' (with hyphens between letters). Ask if that's correct. Keep it short and natural."
        else:
            self.userdata.temp_first_name = None
            self.userdata.first_name_confirmed = False

            logger.debug(f"[DEBUG] User said name was incorrect, asking again...")

            return None, "The user said their name was not correct. Say 'No problem!' and ask for their name again."

    @function_tool
    async def capture_email(self, context: RunContext, email: str):
        """
        Call this when the user has clearly stated their email address for the FIRST time.
        Convert spoken format to standard email format (e.g., 'john at gmail dot com' becomes 'john@gmail.com').

        Args:
            email: The user's email address in standard format with @ and dots
        """
        # Normalize email format
        normalized_email = email.strip().lower()
        normalized_email = normalized_email.replace(" at ", "@").replace(" dot ", ".").replace("dot com", ".com").replace("dot org", ".org")

        # Validate email format with regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, normalized_email)

        if match:
            self.userdata.temp_email = match.group(0)
        else:
            self.userdata.temp_email = normalized_email

        logger.debug(f"[DEBUG] Captured email: {self.userdata.temp_email}")

        return None, f"You just captured the email '{self.userdata.temp_email}'. Now read it back naturally and ask if it's correct. Keep it short."

    @function_tool
    async def confirm_email_correct(self, context: RunContext):
        """
        Call this when the user confirms their email is correct after you read it back naturally.
        Only call this if they expressed agreement.
        """
        self.userdata.email_confirmed = True

        logger.debug(f"[DEBUG] Email '{self.userdata.temp_email}' confirmed by user!")

        # Create user account in database
        user_id = None
        username = None
        try:
            user, username = create_user_account(self.userdata.temp_first_name, self.userdata.temp_email)
            user_id = str(user.id)
            print(f"ONBOARDING_USERNAME: {username}")
            print(f"ONBOARDING_USER_ID: {user_id}")

            # Update state with user information
            self.state.update_user(
                id=user_id,
                name=self.userdata.temp_first_name,
                email=self.userdata.temp_email,
                username=username
            )

            self.state.switch_mode("main_menu")
            self.state.save_state()

            logger.info("[ONBOARDING] User account created successfully")
            logger.info("[ONBOARDING] State updated - ready for main menu")

        except Exception as e:
            logger.error(f"[ERROR] User account creation failed: {str(e)}")

        # Output markers for main.py to capture
        print(f"ONBOARDING_FIRST_NAME: {self.userdata.temp_first_name}")
        print(f"ONBOARDING_EMAIL: {self.userdata.temp_email}")
        print(f"ONBOARDING_COMPLETE")

        # Handoff to MainMenuAgent
        await self._suppress_turn_detection()
        from agent.agents.main_menu_agent import MainMenuAgent
        return MainMenuAgent(state=self.state, userdata=self.userdata)

    @function_tool
    async def email_incorrect_retry(self, context: RunContext, corrected_email: str = None):
        """
        Call this when the user indicates their email was NOT correct.

        The user might respond in two ways:
        1. Simple disagreement: "no", "wrong", "that's not right"
           → Set corrected_email to None, and we'll ask again

        2. Disagreement with correction: "no, it's john@gmail.com", "actually bake at example dot com"
           → Extract the corrected email and pass it as corrected_email parameter
           → This will immediately capture and confirm the new email

        Args:
            corrected_email: The corrected email if user provided it, None if they just said no
        """
        self.userdata.email_retry_count += 1

        logger.debug(f"[DEBUG] Email was incorrect, retry attempt {self.userdata.email_retry_count}/{self.userdata.max_retries}")

        if self.userdata.email_retry_count >= self.userdata.max_retries:
            return None, "Too many retry attempts. Say something like: 'Having trouble with the email. Let's try text input instead - what's your email?' (This should trigger fallback to text mode)"

        if corrected_email:
            normalized_email = corrected_email.strip().lower()
            normalized_email = normalized_email.replace(" at ", "@").replace(" dot ", ".").replace("dot com", ".com").replace("dot org", ".org")

            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            match = re.search(email_pattern, normalized_email)

            if match:
                self.userdata.temp_email = match.group(0)
            else:
                self.userdata.temp_email = normalized_email

            logger.debug(f"[DEBUG] User provided corrected email: {self.userdata.temp_email}")

            return None, f"The user corrected their email to '{self.userdata.temp_email}'. Now read it back naturally and ask if it's correct. Keep it short."
        else:
            self.userdata.temp_email = None
            self.userdata.email_confirmed = False

            logger.debug(f"[DEBUG] User said email was incorrect, asking again...")

            return None, "The user said their email was not correct. Say 'No worries!' and ask for their email again."




class CollectOnboardingDataTask(AgentTask):
    def __init__(
        self,
        userdata,
        state,
        email: str,
        first_name: str,
        chat_ctx = None,
    ):
        super().__init__(
            instructions=("""
                Collect the user's first name and email address.
                Always confirm their email address and spell it out character by character. 
                Wait for the user's validation.
                Once that is done, call the onboarding_to_menu tool.
                """
            ),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="Greet the user warmly and introduce yourself briefly."
        )

    @function_tool
    async def onboarding_to_menu(
        self,
        first_name: str,
        email: str,
    ):
        """
        Call this once the user has provided their first name and email address.

        Args:
            first_name: The user's first name
            email: The user's email address
        """

        # save user to db and perform onboarding logic


        from agent.agents.main_menu_agent import MainMenuAgent
        
        return MainMenuAgent(state=self.state, userdata = self.userdata)



