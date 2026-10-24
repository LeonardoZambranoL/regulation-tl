The input is a product specification, its drawing and the supplied regulation PDFs.
Claude turns the specification into search questions, then two local search methods find passages by related words and by meaning.
A smaller model orders the strongest matches, and the workflow adds neighboring pages and referenced rules.
Claude reads those sources, writes requirements with quotations and checks whether each requirement applies to the product.
The output contains 395 retained requirements with citations; uncertain decisions and unread sources stay visible in separate reports.
The main weakness is incomplete coverage, and the search settings were selected using one known product, so the measured result may not transfer to another product.
