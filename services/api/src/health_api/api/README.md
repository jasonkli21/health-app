# API layer

HTTP routes, authentication dependencies, typed Profile v1 request/response schemas, and transport concerns only. Route handlers delegate to application commands/queries. Error translation, owner binding, request IDs, body limits and cursor validation stay at this boundary; never accept the owner from request data.
