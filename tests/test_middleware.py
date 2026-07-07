import asyncio
from unittest.mock import AsyncMock, patch
from aiogram.types import Message, Chat, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.error_handler import ErrorHandlerMiddleware
from app.middlewares.db_session import DbSessionMiddleware

async def test_middleware_chain():
    print("Starting middleware chain and error handling tests...")

    # Mocks
    chat = Chat(id=123456, type="private")
    user = User(id=7890, is_bot=False, first_name="Test User")
    
    mock_event = AsyncMock(spec=Message)
    mock_event.chat = chat
    mock_event.from_user = user
    
    # 1. Test successful flow
    print("\n--- Test Case 1: Successful Handler Flow ---")
    mock_handler = AsyncMock(return_value="handler_success")
    data = {}
    
    # We mock async_session_maker in db_session to avoid hitting a real DB in this middleware structural test
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session_maker = lambda: mock_session
    
    with patch("app.middlewares.db_session.async_session_maker", mock_session_maker):
        # Call DbSessionMiddleware directly
        db_middleware = DbSessionMiddleware()
        res = await db_middleware(mock_handler, mock_event, data)
        
        # Verify session was added to data and handler was called
        assert data["session"] == mock_session
        mock_handler.assert_called_once()
        assert res == "handler_success"
        print("Verified: DbSessionMiddleware injects session and returns handler response.")

    # 2. Test Exception Rollback and Re-raise in DbSessionMiddleware
    print("\n--- Test Case 2: DbSessionMiddleware Rollback and Re-raise ---")
    mock_throwing_handler = AsyncMock(side_effect=ValueError("Database error simulated"))
    mock_session.reset_mock()
    
    with patch("app.middlewares.db_session.async_session_maker", mock_session_maker):
        db_middleware = DbSessionMiddleware()
        try:
            await db_middleware(mock_throwing_handler, mock_event, data)
            assert False, "DbSessionMiddleware should have re-raised the exception"
        except ValueError as e:
            assert str(e) == "Database error simulated"
            # Verify rollback was called
            mock_session.rollback.assert_called_once()
            print("Verified: DbSessionMiddleware calls rollback() and re-raises exception.")

    # 3. Test ErrorHandlerMiddleware catches and suppresses
    print("\n--- Test Case 3: ErrorHandlerMiddleware exception suppression ---")
    error_middleware = ErrorHandlerMiddleware()
    
    # Mock a throwing handler (simulating what gets re-raised by DbSessionMiddleware)
    mock_throwing_inner_middleware = AsyncMock(side_effect=ValueError("Re-raised error"))
    
    res = await error_middleware(mock_throwing_inner_middleware, mock_event, data)
    # ErrorHandlerMiddleware should return None and suppress the error
    assert res is None
    print("Verified: ErrorHandlerMiddleware catches, logs, and suppresses the exception (returns None).")

    # 4. Test Complete Chain Sequence (Logging -> ErrorHandler -> DbSession -> Handler)
    print("\n--- Test Case 4: Complete Chain Execution Sequence ---")
    
    logging_mw = LoggingMiddleware()
    error_mw = ErrorHandlerMiddleware()
    db_mw = DbSessionMiddleware()
    
    # Throwing handler at the end of the chain
    mock_final_throwing_handler = AsyncMock(side_effect=RuntimeError("Final handler crash"))
    mock_session.reset_mock()
    
    # Reassemble the call chain
    # logging_mw calls error_mw, which calls db_mw, which calls final_handler
    async def run_chain(event, d):
        # logging_mw wrapper
        async def handle_logging(evt, dt):
            # error_mw wrapper
            async def handle_error(ev, dat):
                # db_mw wrapper
                return await db_mw(mock_final_throwing_handler, ev, dat)
            return await error_mw(handle_error, evt, dt)
        return await logging_mw(handle_logging, event, d)

    with patch("app.middlewares.db_session.async_session_maker", mock_session_maker):
        # Run the full chain
        res = await run_chain(mock_event, {})
        
        # Verify suppression at the end of the chain
        assert res is None
        # Verify rollback was executed (proving the exception propagated up through DbSession first)
        mock_session.rollback.assert_called_once()
        print("Verified: Exception propagated out of DbSession (triggering rollback) and was safely suppressed by ErrorHandler.")

    print("\nAll middleware integration tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_middleware_chain())
