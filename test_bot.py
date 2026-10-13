import asyncio
import os
from database import (
    init_db,
    add_user,
    save_movie,
    get_movie_by_id,
    get_movie_by_code,
    search_movies,
    delete_movie,
    get_total_movies,
    get_total_users
)
from services.metadata import clean_movie_title, format_file_size

async def run_tests():
    print("--- 1. Testing Database Initialization ---")
    await init_db()
    assert os.path.exists("movies.db"), "movies.db was not created!"
    print("Database init: PASS")

    print("\n--- 2. Testing User Management ---")
    await add_user(12345678, "moviefan", "John")
    total_u = await get_total_users()
    assert total_u >= 1, "User was not added!"
    print(f"Total users: {total_u} - PASS")

    print("\n--- 3. Testing Movie Indexing & Deep Link Generation ---")
    m_id, code, is_new = await save_movie(
        file_id="BAACAgIAAxkBAAIBY...",
        file_unique_id="unique_spider_man_1080p",
        file_name="Spider-Man.No.Way.Home.2021.1080p.WEB-DL.mkv",
        file_size=2147483648,  # 2 GB
        caption="Spider-Man: No Way Home (2021) 1080p Multi-Audio",
        mime_type="video/x-matroska"
    )
    print(f"Movie saved with ID: {m_id}, Share Code: {code}, Is New: {is_new}")
    assert m_id > 0 and len(code) == 8, "Failed saving movie!"

    # Test idempotency (same unique ID shouldn't duplicate)
    m_id2, code2, is_new2 = await save_movie(
        file_id="BAACAgIAAxkBAAIBY...",
        file_unique_id="unique_spider_man_1080p",
        file_name="Spider-Man.No.Way.Home.2021.1080p.WEB-DL.mkv",
        file_size=2147483648
    )
    assert not is_new2 and m_id == m_id2 and code == code2, "Duplicate file wasn't detected properly!"
    print("Duplicate prevention: PASS")

    print("\n--- 4. Testing Retrieve by Code & ID ---")
    m_by_id = await get_movie_by_id(m_id)
    assert m_by_id and m_by_id["file_name"] == "Spider-Man.No.Way.Home.2021.1080p.WEB-DL.mkv"
    m_by_code = await get_movie_by_code(code)
    assert m_by_code and m_by_code["id"] == m_id
    print("Retrieval by ID & Code: PASS")

    print("\n--- 5. Testing Search with Keyword Tokenization ---")
    # Search "spider man" (different spacing and punctuation)
    res, count = await search_movies("spider man")
    assert count >= 1 and len(res) >= 1, f"Search failed for 'spider man': {count} results"
    print(f"Search 'spider man' matched: {res[0]['file_name']} - PASS")

    # Search with quality tag
    res_q, count_q = await search_movies("spider 1080p")
    assert count_q >= 1, f"Search failed for 'spider 1080p'"
    print(f"Search 'spider 1080p' matched: PASS")

    print("\n--- 6. Testing Metadata Helpers ---")
    cleaned = clean_movie_title("Inception.2010.1080p.BluRay.x264.AAC-ETRG.mp4")
    print(f"Cleaned title: '{cleaned}'")
    assert "Inception" in cleaned and "1080p" not in cleaned and "x264" not in cleaned
    
    formatted_sz = format_file_size(2147483648)
    assert "2.0 GB" in formatted_sz or "2 GB" in formatted_sz
    print(f"Formatted size: {formatted_sz} - PASS")

    print("\n--- 7. Testing Movie Deletion ---")
    del_ok = await delete_movie(m_id)
    assert del_ok, "Failed to delete movie"
    deleted_check = await get_movie_by_id(m_id)
    assert deleted_check is None, "Movie still exists after deletion"
    print("Movie deletion: PASS")

    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
