"""Utility for token-aware chunking to prevent LLM context limit errors."""

from typing import Any, Callable, List, TypeVar

T = TypeVar("T")

class TokenManager:
    """Manages token counting and safe data batching using heuristics."""

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Estimates the number of tokens in a text string.
        Uses a standard heuristic of 4 characters per token.
        """
        if not text:
            return 0
        return len(text) // 4 + 1

    @staticmethod
    def chunk_data(
        items: List[T], 
        max_tokens: int, 
        text_extractor: Callable[[T], str]
    ) -> List[List[T]]:
        """
        Splits a list of items into batches such that the total estimated tokens 
        of the items in any batch does not exceed max_tokens.
        
        Args:
            items: The list of items to chunk.
            max_tokens: The safe token limit for a single batch.
            text_extractor: A function to extract the text content from an item.
            
        Returns:
            A list of batches, where each batch is a list of items.
        """
        batches = []
        current_batch = []
        current_tokens = 0

        for item in items:
            text = text_extractor(item)
            item_tokens = TokenManager.count_tokens(text)

            # If a single item is larger than the max_tokens, it goes in its own batch
            if current_tokens + item_tokens > max_tokens and current_batch:
                batches.append(current_batch)
                current_batch = [item]
                current_tokens = item_tokens
            else:
                current_batch.append(item)
                current_tokens += item_tokens

        if current_batch:
            batches.append(current_batch)

        return batches
